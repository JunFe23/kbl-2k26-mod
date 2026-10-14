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
    "Potential": ("rating_potential",),
    "Durability": DURABILITY_FIELDS,
}

NAME_CHARS = 20  # 성·이름 각각 UTF-16 20자 고정 버퍼 (playerBase+0x00 성, +0x28 이름)
LAST_NAME_OFFSET = 0x00
FIRST_NAME_OFFSET = 0x28
JERSEY_MASK = 0x03F8  # 등번호 = (u16 & 0x3F8) >> 3
PACKED_BASE_KEY = "rating_driving_layup"  # +0x3E1 bit6, post_fade +0x3E2 bit6 → 3바이트 공유
PACKED_PAIR = ("rating_driving_layup", "rating_post_fade")
KG_TO_LB = 2.2046226218
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


def encode_name(text: str) -> bytes:
    if len(text) > NAME_CHARS - 1:
        raise VenueLabError(f"이름이 너무 깁니다({len(text)}자, 최대 {NAME_CHARS - 1}): {text!r}")
    raw = text.encode("utf-16-le")
    return raw + b"\x00" * (NAME_CHARS * 2 - len(raw))


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


# --- 실행 -----------------------------------------------------------------------

ProbeRunner = Callable[[list[str]], dict[str, Any]]


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
            proc = subprocess.run(
                [str(python), str(script), *args, "--out", str(out)],
                cwd=str(script.parent),
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            if out.is_file():
                return json.loads(out.read_text("utf-8-sig"))
            try:
                return json.loads(proc.stdout)
            except json.JSONDecodeError as e:
                raise VenueLabError(
                    f"probe 출력 해석 실패(exit {proc.returncode}): {proc.stderr[-500:]}"
                ) from e

    return run


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


def team_slots(catalog: dict[str, Any], display: str) -> list[dict[str, Any]]:
    teams = [t for t in catalog.get("teams", []) if t.get("team", {}).get("display") == display]
    if not teams:
        found = sorted({t.get("team", {}).get("display", "?") for t in catalog.get("teams", [])})
        raise VenueLabError(f"게임에서 '{display}' 팀을 찾지 못했습니다. 발견된 팀: {found[:40]}")
    if len(teams) > 1:
        raise VenueLabError(f"'{display}' 팀이 {len(teams)}개 발견되었습니다(모호함)")
    slots = sorted(teams[0].get("slots", []), key=lambda s: s["slot"])
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
) -> ApplyReport:
    report = report or ApplyReport()
    check_gate(processes if processes is not None else running_processes())
    catalog = probe(["--bootstrap-team-slot-roster-catalog"])
    if catalog.get("status") != "ok":
        raise VenueLabError(f"팀 목록 생성 실패: {catalog.get('status')} {catalog.get('reason')}")

    for team in plan["teams"]:
        slots = team_slots(catalog, team["nba_slot"])
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
            report.log(stage="plan", status="planned", ops=len(ops), **who)
            if not write:
                for op in ops:
                    report.log(stage="op", status="dry_run", op=_op_dict(op), **who)
                continue
            for op in ops:
                _execute(op, probe, report, who)
    return report


def _op_dict(op: WriteOp) -> dict[str, Any]:
    d = asdict(op)
    d["address"] = hex(op.address)
    for k in ("expected", "new"):
        if isinstance(d[k], bytes):
            d[k] = d[k].hex(" ")
    return d


def _execute(op: WriteOp, probe: ProbeRunner, report: ApplyReport, who: dict[str, Any]) -> None:
    if op.needs_read:
        # 이전값=새값으로 호출한다.
        # 일치하면 그대로(무변경), 다르면 거부되며 실제 바이트를 돌려준다.
        res = probe(WriteOp(op.label, op.address, "bytes", op.new, op.new).cli_args())
        if res.get("status") == "write_readback_ok":
            report.log(stage="op", status="unchanged", op=_op_dict(op), **who)
            return
        actual = res.get("actual_old_hex", "").replace(" ", "")
        if res.get("status") != "rejected" or len(actual) != len(op.new) * 2:
            report.log(
                stage="op",
                status="error",
                reason=f"이전값 읽기 실패: {res.get('reason')}",
                op=_op_dict(op),
                **who,
            )
            return
        op = WriteOp(op.label, op.address, "bytes", bytes.fromhex(actual), op.new)
    res = probe(op.cli_args())
    report.log(
        stage="op",
        status=res.get("status", "unknown"),
        reason=res.get("reason", ""),
        op=_op_dict(op),
        **who,
    )


def write_report(report: ApplyReport, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for e in report.events:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
