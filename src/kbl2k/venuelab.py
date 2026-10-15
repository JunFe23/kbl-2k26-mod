"""2KVenueLab 2.15 명령줄(probe)을 이용한 일괄 로스터 입력 (ADR-0014, ADR-0015).

흐름
  plan  : data/ → 팀별 15명의 게임 입력값(이름·등번호·신장·체중·2K26 능력치) JSON. 게임 불필요.
  apply : 사용자가 오프라인(without EAC)으로 게임을 띄운 상태에서 실행.
          안티치트 확인 → 팀·선수 목록 → 선수별 최신값 읽기 → 쓰기 연산 계산
          → (--apply 일 때만) 쓰기.
          모든 결과는 JSONL 보고서로 남긴다.

쓰기는 모두 VenueLab 의 --direct-guarded-write 를 거친다.
  - 이전값이 예상과 다르면 쓰지 않는다.
  - 쓴 뒤 다시 읽어 확인한다.
필드 오프셋·인코딩은 docs/2k26-player-fields.md 를 따른다.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .ratings import rate_player

# --- 2K26 필드 매핑 -------------------------------------------------------------

DURABILITY_FIELDS = tuple(
    f"rating_{part}_durability"
    for part in (
        "head",
        "neck",
        "back",
        "left_shoulder",
        "right_shoulder",
        "left_elbow",
        "right_elbow",
        "left_hip",
        "right_hip",
        "left_knee",
        "right_knee",
        "left_ankle",
        "right_ankle",
        "left_foot",
        "right_foot",
        "misc",
    )
)

# 우리 능력치 이름 → 2K26 rating 필드 키 (docs/2k26-player-fields.md)
RATING_FIELD_MAP: dict[str, tuple[str, ...]] = {
    "Close Shot": ("rating_close_shot",),
    "Driving Layup": ("rating_driving_layup",),
    "Driving Dunk": ("rating_driving_dunk",),
    "Standing Dunk": ("rating_standing_dunk",),
    "Post Control": ("rating_post_moves",),
    "Post Fade": ("rating_post_fade",),
    "Post Hook": ("rating_post_hook",),
    "Draw Foul": ("rating_draw_foul",),
    "Mid-Range Shot": ("rating_midrange",),
    "Three-Point Shot": ("rating_three_point",),
    "Free Throw": ("rating_free_throw",),
    "Pass Accuracy": ("rating_pass_accuracy",),
    "Ball Handle": ("rating_ball_control",),
    "Speed With Ball": ("rating_speed_with_ball",),
    "Pass IQ": ("rating_passing_iq",),
    "Pass Vision": ("rating_passing_vision",),
    "Hands": ("rating_hands",),
    "Interior Defense": ("rating_interior_defense",),
    "Perimeter Defense": ("rating_perimeter_defense",),
    "Steal": ("rating_steal",),
    "Block": ("rating_block",),
    "Pass Perception": ("rating_pass_perception",),
    "Help Defense IQ": ("rating_help_defense_iq",),
    "Offensive Rebound": ("rating_offensive_rebound",),
    "Defensive Rebound": ("rating_defensive_rebound",),
    "Speed": ("rating_speed",),
    "Agility": ("rating_agility",),
    "Strength": ("rating_strength",),
    "Vertical": ("rating_vertical",),
    "Stamina": ("rating_stamina",),
    "Hustle": ("rating_hustle",),
    "Shot IQ": ("rating_shot_iq",),
    "Offensive Consistency": ("rating_offensive_consistency",),
    "Defensive Consistency": ("rating_defensive_consistency",),
    "Intangibles": ("rating_intangibles",),
    "Durability": DURABILITY_FIELDS,
}

# 게임이 스스로 다시 계산하는 필드 — 쓰지 않는다 (ADR-0015 보충, 2026-10-15 검증 결과)
GAME_MANAGED_FIELDS = ("rating_potential",)

NAME_CHARS = 20

# 팀 레코드(team_pointer 기준) 고정 UTF-16 칸: (오프셋, 칸 크기[문자]) — VenueLab probe 의
# 팀 필드 정의(team_name +0x2E2 50B, city_name +0x314 36B, city_short_name +0x338 14B)
TEAM_TEXT_FIELDS = {
    "team_name": (0x2E2, 25),
    "team_city": (0x314, 18),
    "team_abbr": (0x338, 7),
}  # 성·이름 각각 UTF-16 20자 고정 버퍼 (playerBase+0x00 성, +0x28 이름)
LAST_NAME_OFFSET = 0x00
FIRST_NAME_OFFSET = 0x28
JERSEY_MASK = 0x03F8  # 등번호 = (u16 & 0x3F8) >> 3
PACKED_BASE_KEY = "rating_driving_layup"  # +0x3E1 bit6, post_fade +0x3E2 bit6 → 3바이트 공유
PACKED_PAIR = ("rating_driving_layup", "rating_post_fade")
KG_TO_LB = 2.2046226218
# 생년월일 비트필드 (VenueLab 2.15 블루프린트·쓰기 감사 write_readback_ok, ADR-0018 분석 2)
#   이름 → (playerBase 오프셋, 컨테이너 바이트 수, 시작 비트, 비트 수, 허용 범위)
BIRTH_FIELDS: dict[str, tuple[int, int, int, int, tuple[int, int]]] = {
    "birth_year": (0x10A, 2, 0, 12, (1950, 2015)),
    "birth_month": (0x343, 1, 4, 4, (1, 12)),
    "birth_day": (0x10C, 1, 1, 5, (1, 31)),
}
EAC_PROCESS_NAMES = ("easyanticheat", "easyanticheat_eos", "start_protected_game")


class VenueLabError(Exception):
    pass


def display_to_raw(display: int) -> int:
    """2K26 rating 표시값(25~99) → raw (표시값 = raw/3 + 25)."""
    d = max(25, min(99, int(display)))
    return (d - 25) * 3


def raw_to_display(raw: int) -> int:
    return max(25, min(99, round(25 + raw / 3)))


# --- 이름 ---------------------------------------------------------------------


@dataclass(frozen=True)
class GameName:
    first: str
    last: str
    needs_review: bool = False
    reason: str = ""


def game_name(player: dict[str, Any]) -> GameName:
    """게임용 영문 이름. player.game_name 이 있으면 그대로 쓴다.

    KBL 영문명 규칙:
      - 국내 선수(한글 이름 띄어쓰기 없음) "KIM NAK HYEON" → 성=Kim, 이름=Nakhyeon
      - 외국 선수 "Davon Reed" → 이름=Davon, 성=Reed
      - 이니셜만 있는 표기("KIM S C")는 검토 필요로 표시한다.
    """
    override = player.get("game_name")
    if override:
        return GameName(override["first"], override["last"])
    en = (player.get("name_en") or "").strip()
    if not en:
        return GameName("", player["name_ko"], True, "영문명 없음")
    tokens = en.split()
    # 한글 이름에 띄어쓰기가 없는 국내 선수만 "성 이름" 순서로 본다 (예: 김낙현)
    korean_style = (
        " " not in player["name_ko"]
        and player.get("player_type") == "domestic"
        and player.get("nationality") in ("KR", None)
    )
    if korean_style and len(tokens) >= 2:
        last = tokens[0].capitalize()
        given = tokens[1:]
        first = "".join(given).capitalize()
        if any(len(t) == 1 for t in given):
            return GameName(first, last, True, f"이니셜 표기 '{en}'")
        return GameName(first, last)
    if len(tokens) == 1:
        return GameName("", tokens[0].capitalize(), True, "단일 이름")
    first = " ".join(t if not t.isupper() else t.capitalize() for t in tokens[:-1])
    last = tokens[-1] if not tokens[-1].isupper() else tokens[-1].capitalize()
    review = en.isupper() and len(tokens) > 2
    return GameName(first, last, review, "대문자 3단어 이상 — 성/이름 구분 확인" if review else "")


def encode_name(text: str, chars: int = NAME_CHARS) -> bytes:
    """UTF-16LE 고정 칸(chars 문자, 널 포함)으로 인코딩."""
    if len(text) > chars - 1:
        raise VenueLabError(f"이름이 너무 깁니다({len(text)}자, 최대 {chars - 1}): {text!r}")
    raw = text.encode("utf-16-le")
    return raw + b"\x00" * (chars * 2 - len(raw))


# --- 계획 ---------------------------------------------------------------------


def player_plan(player: dict[str, Any], rules: dict[str, Any]) -> dict[str, Any]:
    r = rate_player(player, rules)
    fields: dict[str, int] = {}
    for attr, keys in RATING_FIELD_MAP.items():
        if attr in r.attributes:
            for k in keys:
                fields[k] = r.attributes[attr].value
    name = game_name(player)
    weight = player.get("weight_kg")
    return {
        "player_id": player["id"],
        "name_ko": player["name_ko"],
        "first_name": name.first,
        "last_name": name.last,
        "name_needs_review": name.needs_review,
        "name_review_reason": name.reason,
        "jersey": player.get("jersey_number"),
        "height_cm": player.get("height_cm"),
        "weight_lb": round(weight * KG_TO_LB, 1) if weight else None,
        "birth_date": player.get("birth_date"),
        "ovr": r.ovr,
        "ratings": fields,
    }


def build_plan(teams: list[dict[str, Any]], rules: dict[str, Any]) -> dict[str, Any]:
    out = []
    for team in teams:
        if not team.get("game_roster") or not team.get("nba_slot"):
            continue
        by_id = {p["id"]: p for p in team["players"]}
        out.append(
            {
                "team_id": team["id"],
                "name_ko": team["name_ko"],
                "nba_slot": team["nba_slot"],
                "identity": team.get("game_identity"),
                "players": [player_plan(by_id[pid], rules) for pid in team["game_roster"]],
            }
        )
    return {"format": "kbl2k-venuelab-plan/1", "game": "nba2k26", "teams": out}


# --- 쓰기 연산 계산 (순수) -------------------------------------------------------


@dataclass
class WriteOp:
    label: str
    address: int
    kind: str  # u8 | u16 | float32 | bytes
    expected: Any
    new: Any
    needs_read: bool = False  # bytes: 실제 이전값을 먼저 읽어야 함(이름)

    def cli_args(self) -> list[str]:
        args = [
            "--direct-guarded-write",
            "--allow-memory-write",
            "--direct-address",
            hex(self.address),
            "--direct-kind",
            self.kind,
            "--direct-label",
            self.label,
        ]
        if self.kind == "u8":
            args += [
                "--direct-expected-old-u8",
                str(self.expected),
                "--direct-new-u8",
                str(self.new),
            ]
        elif self.kind == "u16":
            args += [
                "--direct-expected-old-u16",
                str(self.expected),
                "--direct-new-u16",
                str(self.new),
            ]
        elif self.kind == "float32":
            args += [
                "--direct-expected-old-float",
                repr(float(self.expected)),
                "--direct-new-float",
                repr(float(self.new)),
            ]
        elif self.kind == "bytes":
            args += [
                "--direct-expected-old-hex",
                self.expected.hex(),
                "--direct-new-hex",
                self.new.hex(),
            ]
        else:
            raise VenueLabError(f"지원하지 않는 kind: {self.kind}")
        return args


def op_kwargs(op: WriteOp) -> dict[str, Any]:
    """WriteOp → VenueLab direct_guarded_write 키워드 인자."""
    kw: dict[str, Any] = {
        "address": op.address,
        "value_kind": op.kind,
        "expected_old_float": 0.0,
        "new_float": 0.0,
        "expected_old_u8": 0,
        "new_u8": 0,
        "expected_old_u16": 0,
        "new_u16": 0,
        "expected_old_u64": 0,
        "new_u64": 0,
        "tolerance": 0.01,
        "label": op.label,
        "expected_old_hex": "",
        "new_hex": "",
    }
    if op.kind == "u8":
        kw.update(expected_old_u8=int(op.expected), new_u8=int(op.new))
    elif op.kind == "u16":
        kw.update(expected_old_u16=int(op.expected), new_u16=int(op.new))
    elif op.kind == "float32":
        kw.update(expected_old_float=float(op.expected), new_float=float(op.new))
    elif op.kind == "bytes":
        kw.update(
            expected_old_hex=op.expected.hex() if op.expected is not None else "",
            new_hex=op.new.hex(),
        )
    else:
        raise VenueLabError(f"지원하지 않는 kind: {op.kind}")
    return kw


def _registry(model: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {e["key"]: e for e in model["player"]["field_registry"]}


def plan_writes(model: dict[str, Any], target: dict[str, Any]) -> list[WriteOp]:
    """선수 모델(--inspect-player-base-roster-model 출력)과 목표값 → 바뀌는 항목만 WriteOp 로."""
    if model.get("status") != "ok":
        raise VenueLabError(f"선수 모델 상태 이상: {model.get('status')} {model.get('reason')}")
    player = model["player"]
    base = int(player["player_base"], 16)
    reg = _registry(model)
    ops: list[WriteOp] = []

    # 능력치 (일반 u8)
    for key, display in target["ratings"].items():
        if key in PACKED_PAIR:
            continue
        e = reg.get(key)
        if e is None:
            raise VenueLabError(f"게임 모델에 필드가 없습니다: {key}")
        if e["type"] != "rating_u8" or not e.get("write_enabled"):
            raise VenueLabError(f"예상과 다른 필드 형식: {key} {e['type']}")
        old, new = int(e["raw_rating"]), display_to_raw(display)
        if old != new:
            ops.append(WriteOp(key, base + e["offset_int"], "u8", old, new))

    # 비트필드 쌍: +0x3E1..+0x3E3 3바이트를 한 번에
    a, b = (reg[k] for k in PACKED_PAIR)
    if b["offset_int"] != a["offset_int"] + 1 or a["start_bit"] != 6 or b["start_bit"] != 6:
        raise VenueLabError("비트필드 배치가 예상(+0x3E1/+0x3E2, bit 6)과 다릅니다")
    c1, c2 = int(a["container_u16"]), int(b["container_u16"])
    if (c1 >> 8) != (c2 & 0xFF):
        raise VenueLabError("비트필드 컨테이너가 서로 맞지 않습니다(모델 불일치)")
    v = c1 | ((c2 >> 8) << 16)  # 3바이트 little-endian
    nv = v
    for i, key in enumerate(PACKED_PAIR):
        shift = 6 + 8 * i
        if key in target["ratings"]:
            nv = (nv & ~(0xFF << shift)) | (display_to_raw(target["ratings"][key]) << shift)
    if nv != v:
        ops.append(
            WriteOp(
                "rating_driving_layup+post_fade",
                base + a["offset_int"],
                "bytes",
                v.to_bytes(3, "little"),
                nv.to_bytes(3, "little"),
            )
        )

    # 등번호 (bit 3~9)
    if target.get("jersey") is not None:
        j = reg["jersey"]
        old = int(j["value"])
        new = (old & ~JERSEY_MASK) | ((int(target["jersey"]) & 0x7F) << 3)
        if old != new:
            ops.append(WriteOp("jersey", base + j["offset_int"], "u16", old, new))

    # 체중 (float32 파운드)
    if target.get("weight_lb") is not None:
        w = reg["weight"]
        if abs(float(w["value"]) - target["weight_lb"]) > 0.05:
            ops.append(
                WriteOp(
                    "weight",
                    base + w["offset_int"],
                    "float32",
                    float(w["value"]),
                    float(target["weight_lb"]),
                )
            )

    # 신장 (Appearance Data u16 = cm×100)
    if target.get("height_cm") is not None:
        h = reg["appearance_height_cm"]
        old, new = int(h["value"]), round(float(target["height_cm"]) * 100)
        if old != new:
            ops.append(WriteOp("appearance_height_cm", int(h["address"], 16), "u16", old, new))

    # 이름 (UTF-16 20자 고정 버퍼) — 실제 이전 바이트는 실행 시 읽는다
    for label, off, text in (
        ("last_name", LAST_NAME_OFFSET, target.get("last_name")),
        ("first_name", FIRST_NAME_OFFSET, target.get("first_name")),
    ):
        if text is None:
            continue
        current = player.get(label)
        if current != text:
            ops.append(
                WriteOp(label, base + off, "bytes", None, encode_name(text), needs_read=True)
            )
    return ops


def birth_read_requests(base: int) -> list[dict[str, int]]:
    """생년월일 컨테이너를 읽을 주소 목록 (BIRTH_FIELDS 순서)."""
    return [{"address": base + off, "length": n} for off, n, *_ in BIRTH_FIELDS.values()]


def plan_birth_writes(
    base: int, birth_date: str, containers: list[int]
) -> tuple[list[WriteOp], dict[str, int], str]:
    """현재 컨테이너 값 → (쓰기 연산, 현재 해석값, 문제).

    현재 값이 생년월일로 해석되지 않으면(범위 밖) 형식 가정이 틀렸을 수 있으므로 쓰지 않는다.
    """
    y, m, d = (int(x) for x in birth_date.split("-"))
    target = {"birth_year": y, "birth_month": m, "birth_day": d}
    ops: list[WriteOp] = []
    current: dict[str, int] = {}
    for (label, (off, n, start, bits, (lo, hi))), old in zip(
        BIRTH_FIELDS.items(), containers, strict=True
    ):
        mask = ((1 << bits) - 1) << start
        current[label] = (old & mask) >> start
        if not lo <= current[label] <= hi:
            return (
                [],
                current,
                f"현재 {label}={current[label]} 이 범위({lo}~{hi}) 밖 — 형식 확인 필요",
            )
        new = (old & ~mask) | (target[label] << start)
        if new != old:
            ops.append(WriteOp(label, base + off, "u16" if n == 2 else "u8", old, new))
    return ops, current, ""


# --- 실행 -----------------------------------------------------------------------

ProbeRunner = Callable[[list[str]], dict[str, Any]]
OWNER_TABLE_CATALOG = "kbl2k:owner-table-catalog"  # 내부 전용 의사 명령
BOOTSTRAP_CATALOG = "--bootstrap-team-slot-roster-catalog"
BATCH_WRITE = "kbl2k:batch-write"  # 내부 전용: 한 프로세스에서 guarded write 연속 실행
READ_BYTES = "kbl2k:read-bytes"  # 내부 전용: 메모리 읽기만 (ReadProcessMemory)

READ_WORKER = r"""
import json, sys
sys.path.insert(0, sys.argv[1])
import roster_live_memory_probe as p
reqs = json.load(open(sys.argv[2], encoding='utf-8'))
procs = p.find_processes('NBA2K26.exe')
out = []
for q in reqs:
    if not procs:
        out.append(None)
        continue
    r = p.read_process_bytes(int(procs[0]['pid']), int(q['address']), int(q['length']))
    ok = r.get('ok') and len(r.get('data', b'')) == int(q['length'])
    out.append(r['data'].hex() if ok else None)
json.dump(out, open(sys.argv[3], 'w', encoding='utf-8'))
"""

# VenueLab 파이썬으로 실행되는 일괄 쓰기 워커. 각 쓰기는 VenueLab 의 direct_guarded_write 를
# 그대로 호출한다(이전값 확인 → 쓰기 → 다시 읽기). needs_read 항목은 이전값=새값 호출로
# 실제 바이트를 먼저 읽는다(무변경).
BATCH_WORKER = r"""
import json, sys
sys.path.insert(0, sys.argv[1])
import roster_live_memory_probe as p
ops = json.load(open(sys.argv[2], encoding='utf-8'))
out = []
for o in ops:
    kw = dict(o['kwargs'])
    if o.get('needs_read'):
        r = p.direct_guarded_write('NBA2K26.exe', **{**kw, 'expected_old_hex': kw['new_hex']})
        if r.get('status') == 'write_readback_ok':
            out.append({'status': 'unchanged', 'reason': 'already equal'})
            continue
        a = (r.get('actual_old_hex') or '').replace(' ', '')
        if r.get('status') != 'rejected' or len(a) != len(kw['new_hex']):
            out.append({'status': 'error', 'reason': 'read failed: ' + str(r.get('reason'))})
            continue
        kw['expected_old_hex'] = a
    r = p.direct_guarded_write('NBA2K26.exe', **kw)
    r['used_expected_old_hex'] = kw.get('expected_old_hex', '')
    out.append(r)
json.dump(out, open(sys.argv[3], 'w', encoding='utf-8'), default=str)
"""


def make_probe_runner(venuelab_dir: Path, timeout: float = 600) -> ProbeRunner:
    venuelab_dir = Path(venuelab_dir)
    python = venuelab_dir / "app" / "python" / "python.exe"
    script = venuelab_dir / "app" / "tools" / "roster_live_memory_probe.py"
    for p in (python, script):
        if not p.is_file():
            raise VenueLabError(f"VenueLab 파일이 없습니다: {p}")

    def run(args: list[str]) -> dict[str, Any]:
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out.json"
            if args and args[0] in (BATCH_WRITE, READ_BYTES):
                ops_path = Path(td) / "ops.json"
                ops_path.write_text(args[1], "utf-8")
                worker = BATCH_WORKER if args[0] == BATCH_WRITE else READ_WORKER
                cmd = [str(python), "-c", worker, str(script.parent), str(ops_path), str(out)]
            elif args == [OWNER_TABLE_CATALOG]:
                # CLI 플래그가 없는 읽기 전용 함수 — VenueLab 앱의 팀 목록과 같은 방식
                code = (
                    "import json,sys;sys.path.insert(0,sys.argv[1]);"
                    "import roster_live_memory_probe as p;"
                    "r=p.build_team_slot_roster_catalog_from_owner_tables('NBA2K26.exe');"
                    "open(sys.argv[2],'w',encoding='utf-8').write(json.dumps(r,default=str))"
                )
                cmd = [str(python), "-c", code, str(script.parent), str(out)]
            else:
                cmd = [str(python), str(script), *args, "--out", str(out)]
            proc = subprocess.run(
                cmd,
                cwd=str(script.parent),
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            if out.is_file():
                data = json.loads(out.read_text("utf-8-sig"))
                return {"results": data} if isinstance(data, list) else data
            try:
                return json.loads(proc.stdout)
            except json.JSONDecodeError as e:
                raise VenueLabError(
                    f"probe 출력 해석 실패(exit {proc.returncode}): {proc.stderr[-500:]}"
                ) from e

    return run


def catalog_is_usable(catalog: dict[str, Any]) -> bool:
    """팀 목록이 쓸 만한지: 상태 ok 이고, 이름이 정상인 팀(“Team 0x…” 아님)이 2개 이상."""
    if catalog.get("status") != "ok":
        return False
    named = [
        t
        for t in catalog.get("teams", [])
        if (d := t.get("team", {}).get("display", "")) and not d.startswith("Team 0x")
    ]
    return len(named) >= 2


def read_catalog(probe: ProbeRunner) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """선수·팀 테이블 방식 → 실패 시 구조 스캔. (사용한 목록, 시도 기록)"""
    tried: list[dict[str, Any]] = []
    last: dict[str, Any] = {}
    for method in (OWNER_TABLE_CATALOG, BOOTSTRAP_CATALOG):
        try:
            cat = probe([method])
        except VenueLabError as e:
            tried.append({"method": method, "status": "error", "reason": str(e)[:300]})
            continue
        ok = catalog_is_usable(cat)
        tried.append(
            {
                "method": method,
                "status": cat.get("status"),
                "usable": ok,
                "team_count": cat.get("team_count"),
            }
        )
        last = cat
        if ok:
            return cat, tried
    return last or {"status": "not_found", "teams": []}, tried


def running_processes() -> list[str]:
    out = subprocess.run(["tasklist", "/fo", "csv", "/nh"], capture_output=True, text=True).stdout
    return [line.split('","')[0].strip('"') for line in out.splitlines() if line.strip()]


def check_gate(processes: list[str]) -> None:
    names = [p.lower().removesuffix(".exe") for p in processes]
    eac = [p for p in names if p in EAC_PROCESS_NAMES]
    if eac:
        raise VenueLabError(
            f"안티치트 관련 프로세스가 실행 중입니다({', '.join(eac)}). "
            "Steam 에서 'NBA 2K26 without EAC (offline only)' 로 다시 실행하세요."
        )
    if "nba2k26" not in names:
        raise VenueLabError("NBA2K26.exe 가 실행 중이 아닙니다.")


NBA_TEAM_INDEX_MAX = 29  # 2K 팀 테이블 0~29번 = 현역 NBA 팀 (클래식·확장팀은 그 뒤)


def team_index(catalog: dict[str, Any], entry: dict[str, Any]) -> int | None:
    """팀 레코드의 팀 테이블 번호. owner_tables 정보가 없거나 맞지 않으면 None."""
    table = (catalog.get("owner_tables") or {}).get("Team") or {}
    try:
        base = int(str(table["base"]), 0)
        stride = int(table["stride"])
        ptr = int(str(entry["team_pointer"]), 0)
    except (KeyError, TypeError, ValueError):
        return None
    off = ptr - base
    if stride <= 0 or off < 0 or off % stride:
        return None
    return off // stride


def describe_team(catalog: dict[str, Any], entry: dict[str, Any]) -> dict[str, Any]:
    slots = sorted(entry.get("slots", []), key=lambda s: s["slot"])
    return {
        "team_pointer": entry.get("team_pointer"),
        "team_index": team_index(catalog, entry),
        "abbr": entry.get("team", {}).get("abbr"),
        "players": [s["player"].get("display_name") for s in slots if s.get("player")][:5],
    }


def team_display_names(
    team_plan: dict[str, Any], aliases: dict[str, list[str]] | None = None
) -> list[str]:
    """게임에서 팀을 찾을 이름들: 교체 전 NBA 이름, 교체 후 이름, 별칭(예: MyNBA 이전 후)."""
    names = [team_plan["nba_slot"]]
    ident = team_plan.get("identity")
    if ident:
        names.append(f"{ident['city']} {ident['name']}")
    names += (aliases or {}).get(team_plan["nba_slot"], [])
    return names


def select_team_any(catalog: dict[str, Any], names: list[str]) -> tuple[dict[str, Any], str]:
    errors = []
    for name in names:
        try:
            entry, decision = select_team(catalog, name)
            return entry, f"'{name}' — {decision}"
        except VenueLabError as e:
            errors.append(str(e)[:200])
    raise VenueLabError(" / ".join(errors))


def plan_team_writes(entry: dict[str, Any], identity: dict[str, Any] | None) -> list[WriteOp]:
    """팀 도시·팀명·약어 쓰기. 이미 같으면 생략, 이전 바이트는 실행 시 읽는다."""
    if not identity:
        return []
    base = int(str(entry["team_pointer"]), 0)
    current = entry.get("team", {})
    want = {
        "team_name": (identity["name"], current.get("nickname")),
        "team_city": (identity["city"], current.get("city")),
        "team_abbr": (identity["abbr"], current.get("abbr")),
    }
    ops = []
    for label, (text, now) in want.items():
        off, chars = TEAM_TEXT_FIELDS[label]
        if now != text:
            ops.append(WriteOp(label, base + off, "bytes", None, encode_name(text, chars), True))
    return ops


def select_team(catalog: dict[str, Any], display: str) -> tuple[dict[str, Any], str]:
    """display 이름의 팀 레코드를 고른다.

    같은 이름이 여럿이면(클래식 팀 등) 현역 번호대(0~29)가 하나일 때만 고르고, 아니면 멈춘다.
    """
    teams = [t for t in catalog.get("teams", []) if t.get("team", {}).get("display") == display]
    if not teams:
        found = sorted({t.get("team", {}).get("display", "?") for t in catalog.get("teams", [])})
        raise VenueLabError(f"게임에서 '{display}' 팀을 찾지 못했습니다. 발견된 팀: {found[:40]}")
    if len(teams) == 1:
        return teams[0], "유일"
    current = [
        t for t in teams if (i := team_index(catalog, t)) is not None and i <= NBA_TEAM_INDEX_MAX
    ]
    if len(current) == 1:
        others = [describe_team(catalog, t) for t in teams if t is not current[0]]
        return current[0], f"같은 이름 {len(teams)}개 중 현역 번호대(0~29) 선택. 제외: {others}"
    detail = [describe_team(catalog, t) for t in teams]
    raise VenueLabError(f"'{display}' 팀이 {len(teams)}개 발견되었습니다(모호함): {detail}")


def team_slots(catalog: dict[str, Any], display: str) -> list[dict[str, Any]]:
    entry, _ = select_team(catalog, display)
    slots = sorted(entry.get("slots", []), key=lambda s: s["slot"])
    return [s for s in slots if s.get("player") and s.get("pointer")]


@dataclass
class ApplyReport:
    events: list[dict[str, Any]] = field(default_factory=list)

    def log(self, **kw: Any) -> None:
        self.events.append(kw)

    def count(self, status: str) -> int:
        return sum(1 for e in self.events if e.get("status") == status)


def apply_plan(
    plan: dict[str, Any],
    probe: ProbeRunner,
    *,
    write: bool = False,
    processes: list[str] | None = None,
    report: ApplyReport | None = None,
    progress: Callable[[str], None] = lambda msg: None,
    catalog_path: Path | None = None,
    aliases: dict[str, list[str]] | None = None,
) -> ApplyReport:
    report = report or ApplyReport()
    progress("1/3 안전 확인 (안티치트·게임 실행 여부)")
    check_gate(processes if processes is not None else running_processes())
    progress("2/3 게임에서 팀·선수 목록 읽는 중 — 1~3분 걸릴 수 있습니다. 기다려 주세요")
    catalog, tried = read_catalog(probe)
    if catalog_path is not None:
        catalog_path.parent.mkdir(parents=True, exist_ok=True)
        catalog_path.write_text(json.dumps(catalog, ensure_ascii=False), "utf-8")
    report.log(
        stage="catalog",
        status=catalog.get("status"),
        team_count=catalog.get("team_count"),
        source=catalog.get("source") or catalog.get("mode"),
        tried=tried,
        path=str(catalog_path) if catalog_path else None,
    )
    if not catalog_is_usable(catalog):
        raise VenueLabError(
            f"팀 목록을 제대로 읽지 못했습니다(시도: {tried}). 로스터 화면에서 다시 실행하세요."
        )

    for team in plan["teams"]:
        entry, decision = select_team_any(catalog, team_display_names(team, aliases))
        report.log(
            stage="team",
            team=team["nba_slot"],
            status="selected",
            decision=decision,
            **describe_team(catalog, entry),
        )
        slots = [
            s
            for s in sorted(entry.get("slots", []), key=lambda s: s["slot"])
            if s.get("player") and s.get("pointer")
        ]
        team_ops = plan_team_writes(entry, team.get("identity"))
        team_who = dict(
            team=team["nba_slot"],
            slot=0,
            player_base=entry.get("team_pointer"),
            from_player=entry.get("team", {}).get("display"),
            to_player=" ".join((team.get("identity") or {}).get(k, "") for k in ("city", "name")),
        )
        if write:
            _execute_batch(team_ops, probe, report, team_who)
        else:
            for op in team_ops:
                report.log(stage="op", status="dry_run", op=_op_dict(op), **team_who)
        progress(f"3/3 {team['nba_slot']}: 선수 {min(len(slots), len(team['players']))}명 처리")
        targets = team["players"]
        if len(slots) < len(targets):
            report.log(
                stage="team",
                team=team["nba_slot"],
                status="warning",
                reason=f"게임 선수 {len(slots)}명 < 입력 {len(targets)}명 (앞에서부터 반영)",
            )
        for slot, target in zip(slots, targets, strict=False):
            pb = slot["pointer"]
            who = dict(
                team=team["nba_slot"],
                slot=slot["slot"],
                player_base=pb,
                from_player=slot["player"].get("display_name"),
                to_player=target["name_ko"],
            )
            try:
                model = probe(["--inspect-player-base-roster-model", "--player-base", pb])
                ops = plan_writes(model, target)
            except VenueLabError as e:
                report.log(stage="plan", status="error", reason=str(e), **who)
                continue
            if target.get("birth_date"):
                ops += _birth_ops(
                    probe, int(model["player"]["player_base"], 16), target, report, who
                )
            ctx = model.get("current_context") or {}
            report.log(
                stage="plan",
                status="planned",
                ops=len(ops),
                context=ctx.get("detected"),
                context_confidence=ctx.get("confidence"),
                save_authoritative=(model.get("save_authoritative_filter") or {}).get("allowed"),
                **who,
            )
            if not write:
                for op in ops:
                    report.log(stage="op", status="dry_run", op=_op_dict(op), **who)
                continue
            _execute_batch(ops, probe, report, who)
    return report


def read_containers(probe: ProbeRunner, reqs: list[dict[str, int]]) -> list[int | None]:
    """주소별 리틀엔디언 정수. 읽기 실패는 None."""
    res = probe([READ_BYTES, json.dumps(reqs)]).get("results")
    if not isinstance(res, list) or len(res) != len(reqs):
        raise VenueLabError(f"메모리 읽기 결과 이상: {str(res)[:200]}")
    return [int.from_bytes(bytes.fromhex(h), "little") if h else None for h in res]


def _birth_ops(
    probe: ProbeRunner, base: int, target: dict[str, Any], report: ApplyReport, who: dict
) -> list[WriteOp]:
    try:
        containers = read_containers(probe, birth_read_requests(base))
    except VenueLabError as e:
        report.log(stage="birth", status="error", reason=str(e), **who)
        return []
    if None in containers:
        report.log(stage="birth", status="error", reason="생년월일 읽기 실패", **who)
        return []
    ops, current, problem = plan_birth_writes(base, target["birth_date"], containers)
    report.log(
        stage="birth",
        status="skipped" if problem else "checked",
        reason=problem,
        current=current,
        target=target["birth_date"],
        **who,
    )
    return ops


def _op_dict(op: WriteOp) -> dict[str, Any]:
    d = asdict(op)
    d["address"] = hex(op.address)
    for k in ("expected", "new"):
        if isinstance(d[k], bytes):
            d[k] = d[k].hex(" ")
    return d


def _execute_batch(
    ops: list[WriteOp], probe: ProbeRunner, report: ApplyReport, who: dict[str, Any]
) -> None:
    if not ops:
        return
    payload = json.dumps([{"kwargs": op_kwargs(o), "needs_read": o.needs_read} for o in ops])
    res = probe([BATCH_WRITE, payload])
    results = res.get("results")
    if not isinstance(results, list) or len(results) != len(ops):
        report.log(
            stage="op", status="error", reason=f"일괄 쓰기 결과 이상: {str(res)[:300]}", **who
        )
        return
    for op, r in zip(ops, results, strict=True):
        d = _op_dict(op)
        if r.get("used_expected_old_hex"):
            d["expected"] = r["used_expected_old_hex"]
        report.log(
            stage="op", status=r.get("status", "unknown"), reason=r.get("reason", ""), op=d, **who
        )


def write_report(report: ApplyReport, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for e in report.events:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")


# --- 팀 레코드 분석 (ADR-0018 후속, 읽기 전용) ---------------------------------

TEAM_RECORD_LENGTH = 5672  # 팀 레코드 간격(stride)


def capture_team(
    probe: ProbeRunner,
    names: list[str],
    label: str,
    *,
    processes: list[str] | None = None,
    length: int = TEAM_RECORD_LENGTH,
) -> dict[str, Any]:
    """이름으로 팀을 찾아 팀 레코드 바이트를 캡처한다(쓰기 없음)."""
    check_gate(processes if processes is not None else running_processes())
    catalog, tried = read_catalog(probe)
    if not catalog_is_usable(catalog):
        raise VenueLabError(f"팀 목록을 읽지 못했습니다: {tried}")
    entry, decision = select_team_any(catalog, names)
    cap = probe([
        "--capture-team-record-state", "--team-pointer", str(entry["team_pointer"]),
        "--team-record-label", label, "--team-record-capture-length", str(length),
    ])  # fmt: skip
    if not cap.get("raw_hex"):
        raise VenueLabError(f"캡처 실패: {cap.get('status')} {cap.get('reason')}")
    return {
        "label": label,
        "team": entry.get("team", {}),
        "team_pointer": entry["team_pointer"],
        "decision": decision,
        "raw_hex": cap["raw_hex"],
        "sha256": cap.get("sha256"),
    }


def _utf16_preview(b: bytes) -> str:
    try:
        s = b.decode("utf-16-le", errors="strict")
    except UnicodeDecodeError:
        return ""
    s = s.split("\x00")[0]
    return s if s and all(32 <= ord(c) < 0x10000 for c in s) else ""


def diff_team_captures(a_hex: str, b_hex: str, context: int = 0) -> list[dict[str, Any]]:
    """두 캡처의 바뀐 바이트 구간. 4바이트 이내로 붙은 변경은 한 구간으로 묶는다."""
    a = bytes.fromhex(a_hex.replace(" ", ""))
    b = bytes.fromhex(b_hex.replace(" ", ""))
    n = min(len(a), len(b))
    diffs = [i for i in range(n) if a[i] != b[i]]
    ranges: list[list[int]] = []
    for i in diffs:
        if ranges and i - ranges[-1][1] <= 4:
            ranges[-1][1] = i
        else:
            ranges.append([i, i])
    out = []
    for s, e in ranges:
        s0, e0 = max(0, s - context), min(n, e + 1 + context)
        start = s0 - (s0 % 2)
        out.append({
            "offset": f"+0x{s:X}",
            "length": e - s + 1,
            "before": a[s0:e0].hex(" "),
            "after": b[s0:e0].hex(" "),
            "before_text": _utf16_preview(a[start:start + 64]),
            "after_text": _utf16_preview(b[start:start + 64]),
        })  # fmt: skip
    return out


# --- MyNBA 이전 도시 이름 (ADR-0018 분석 3) --------------------------------------
# 이전한 팀은 도시 이름을 팀 레코드 문자열이 아니라 도시 테이블에서 가져온다.
#   팀 +0xFD0 = 도시 레코드 포인터, 팀 +0xE98(16바이트) = 도시 ID
#   도시 레코드(간격 0x80): +0x00 약어 UTF-16, +0x0E 도시 이름 ASCII(18바이트 칸),
#   +0x20 주 약어 UTF-16, +0x38 도시 ID(8바이트 두 덩어리, 팀 쪽과 순서가 반대)
# 도시 테이블은 게임 데이터라 세이브에 저장되지 않는다고 본다 → 게임을 켤 때마다 다시 쓴다.

CITY_POINTER_OFFSET = 0xFD0
CITY_ID_OFFSET = 0xE98
CITY_RECORD_LENGTH = 0x80
CITY_NAME_OFFSET = 0x0E
CITY_NAME_BYTES = 18


def city_id_matches(team_raw: bytes, city_raw: bytes) -> bool:
    tid = team_raw[CITY_ID_OFFSET : CITY_ID_OFFSET + 16]
    if not any(tid):
        return False  # 이전하지 않은 팀
    return tid[:8] == city_raw[0x40:0x48] and tid[8:] == city_raw[0x38:0x40]


def city_name(city_raw: bytes) -> str:
    raw = city_raw[CITY_NAME_OFFSET : CITY_NAME_OFFSET + CITY_NAME_BYTES]
    return raw.split(b"\0")[0].decode("ascii", errors="replace")


def encode_city_name(text: str) -> bytes:
    if not text.isascii() or not text.strip():
        raise VenueLabError(f"도시 이름은 영문(ASCII)만 가능합니다: {text!r}")
    if len(text) > CITY_NAME_BYTES - 1:
        raise VenueLabError(f"도시 이름이 너무 깁니다({len(text)}자, 최대 {CITY_NAME_BYTES - 1})")
    return text.encode("ascii").ljust(CITY_NAME_BYTES, b"\0")


def plan_city_write(team_raw: bytes, city_raw: bytes, new_name: str) -> WriteOp | None:
    """팀 레코드·도시 레코드 → 도시 이름 쓰기 연산. 이미 같으면 None."""
    if len(city_raw) < CITY_RECORD_LENGTH:
        raise VenueLabError("도시 레코드를 읽지 못했습니다")
    if not city_id_matches(team_raw, city_raw):
        raise VenueLabError(
            "팀이 가리키는 도시 레코드의 ID 가 팀의 도시 ID 와 다릅니다"
            "(이전하지 않은 팀이거나 구조가 예상과 다름) — 쓰지 않습니다"
        )
    ptr = int.from_bytes(team_raw[CITY_POINTER_OFFSET : CITY_POINTER_OFFSET + 8], "little")
    old = city_raw[CITY_NAME_OFFSET : CITY_NAME_OFFSET + CITY_NAME_BYTES]
    new = encode_city_name(new_name)
    if old == new:
        return None
    return WriteOp("city_table_name", ptr + CITY_NAME_OFFSET, "bytes", old, new)


# 경기장 레코드 (팀 +0xFC8 포인터): +0x00 경기장 이름 UTF-16, +0x82 도시 UTF-16 24자 칸,
# +0xB2 경기장 번호 ASCII("003"), +0xBA "arena_003_int". 이전하면 도시가 이전 도시로 바뀐다.
ARENA_POINTER_OFFSET = 0xFC8
ARENA_RECORD_LENGTH = 0x100
ARENA_CITY_OFFSET = 0x82
ARENA_CITY_CHARS = 24


def arena_city(arena_raw: bytes) -> str:
    raw = arena_raw[ARENA_CITY_OFFSET : ARENA_CITY_OFFSET + ARENA_CITY_CHARS * 2]
    return raw.decode("utf-16-le", errors="replace").split("\0")[0]


def plan_arena_city_write(team_raw: bytes, arena_raw: bytes, new_name: str) -> WriteOp | None:
    """경기장 레코드의 도시 칸 쓰기 연산. 레코드 모양이 예상과 다르면 거부."""
    if len(arena_raw) < ARENA_RECORD_LENGTH or not arena_raw[0xBA:0xC0] == b"arena_":
        raise VenueLabError(
            "경기장 레코드 모양이 예상과 다릅니다('arena_' 표시 없음) — 쓰지 않습니다"
        )
    if not arena_city(arena_raw).strip():
        raise VenueLabError("경기장 레코드의 도시 칸이 비어 있습니다 — 쓰지 않습니다")
    ptr = int.from_bytes(team_raw[ARENA_POINTER_OFFSET : ARENA_POINTER_OFFSET + 8], "little")
    old = arena_raw[ARENA_CITY_OFFSET : ARENA_CITY_OFFSET + ARENA_CITY_CHARS * 2]
    new = encode_name(new_name, chars=ARENA_CITY_CHARS)
    if old == new:
        return None
    return WriteOp("arena_city", ptr + ARENA_CITY_OFFSET, "bytes", old, new)


def rename_relocated_city(
    probe: ProbeRunner,
    names: list[str],
    new_name: str,
    *,
    write: bool = False,
    processes: list[str] | None = None,
) -> dict[str, Any]:
    """이전한 팀의 도시 표시 이름을 바꾼다(메모리). 도시 테이블 + 경기장 레코드."""
    cap = capture_team(probe, names, "city", processes=processes)
    team_raw = bytes.fromhex(cap["raw_hex"])
    city_ptr = int.from_bytes(team_raw[CITY_POINTER_OFFSET : CITY_POINTER_OFFSET + 8], "little")
    arena_ptr = int.from_bytes(team_raw[ARENA_POINTER_OFFSET : ARENA_POINTER_OFFSET + 8], "little")
    reqs = [
        {"address": city_ptr, "length": CITY_RECORD_LENGTH},
        {"address": arena_ptr, "length": ARENA_RECORD_LENGTH},
    ]
    hexes = probe([READ_BYTES, json.dumps(reqs)]).get("results") or [None, None]
    city_raw, arena_raw = (bytes.fromhex(h) if h else b"" for h in hexes)
    fields = [
        ("city_table", city_name(city_raw), plan_city_write(team_raw, city_raw, new_name)),
        ("arena", arena_city(arena_raw), plan_arena_city_write(team_raw, arena_raw, new_name)),
    ]
    results = []
    for field_name, before, op in fields:
        status = "unchanged" if op is None else ("planned" if not write else "")
        item = {"field": field_name, "from": before, "to": new_name, "status": status}
        if op is not None and write:
            r = probe([BATCH_WRITE, json.dumps([{"kwargs": op_kwargs(op), "needs_read": False}])])
            rr = (r.get("results") or [{}])[0]
            item["status"], item["reason"] = rr.get("status", "unknown"), rr.get("reason", "")
        results.append(item)
    return {"team": cap["team"], "fields": results}
