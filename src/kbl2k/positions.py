"""KBL 포지션(G/F/C)과 2K26 포지션(PG/SG/SF/PF/C) 관리.

2K 포지션은 사실 데이터가 아니라 모드 설계값이므로 사용자가 직접 정한다.
작업 흐름: `kbl2k positions export` → 엑셀에서 primary/secondary 입력 → `kbl2k positions import`.
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .dataset import TEAMS_DIR, load_dataset
from .issues import Issue, error, warning

POSITIONS_2K = ("PG", "SG", "SF", "PF", "C")
KBL_TO_2K: dict[str, tuple[str, ...]] = {
    "G": ("PG", "SG"),
    "F": ("SF", "PF"),
    "C": ("C",),
}
CSV_COLUMNS = (
    "team_id", "player_id", "jersey_number", "name_ko", "position_kbl",
    "suggested", "primary", "secondary",
)  # fmt: skip


def position_issues(player: dict[str, Any], file: str, path: str) -> list[Issue]:
    """2K 주 포지션이 KBL 포지션과 어울리지 않으면 경고(의도한 경우도 있으므로 오류 아님)."""
    kbl, pos = player.get("position_kbl"), player.get("positions") or []
    if not kbl or not pos or pos[0] in KBL_TO_2K[kbl]:
        return []
    return [
        warning(
            file,
            f"{path}.positions",
            f"주 포지션 {pos[0]} 이 KBL 포지션 {kbl}({'/'.join(KBL_TO_2K[kbl])}) 과 다름",
        )
    ]


def export_csv(teams: list[dict[str, Any]]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(CSV_COLUMNS)
    for team in teams:
        for p in sorted(
            team["players"], key=lambda p: (p["jersey_number"] is None, p["jersey_number"])
        ):
            pos = p.get("positions") or []
            kbl = p.get("position_kbl")
            w.writerow([
                team["id"], p["id"], p["jersey_number"] if p["jersey_number"] is not None else "",
                p["name_ko"], kbl or "", "/".join(KBL_TO_2K.get(kbl, ())),
                pos[0] if pos else "", pos[1] if len(pos) > 1 else "",
            ])  # fmt: skip
    return buf.getvalue()


@dataclass(frozen=True)
class PositionChange:
    file: str
    player_id: str
    name_ko: str
    old: tuple[str, ...]
    new: tuple[str, ...]


def parse_csv(text: str, csv_name: str) -> tuple[dict[str, list[str]], list[Issue]]:
    """CSV → {player_id: [primary, secondary?]}. 빈 primary 는 '미정'(빈 배열)."""
    issues: list[Issue] = []
    rows = list(csv.DictReader(io.StringIO(text.lstrip("﻿"))))
    if rows and not {"player_id", "primary", "secondary"} <= set(rows[0]):
        return {}, [error(csv_name, "", "player_id, primary, secondary 열이 필요합니다")]

    out: dict[str, list[str]] = {}
    for n, row in enumerate(rows, start=2):  # 1행은 헤더
        where = f"{n}행"
        pid = (row.get("player_id") or "").strip()
        primary = (row.get("primary") or "").strip().upper()
        secondary = (row.get("secondary") or "").strip().upper()
        if not pid:
            issues.append(error(csv_name, where, "player_id 가 비어 있습니다"))
            continue
        if pid in out:
            issues.append(error(csv_name, where, f"'{pid}' 가 여러 번 나옵니다"))
            continue
        bad = [v for v in (primary, secondary) if v and v not in POSITIONS_2K]
        if bad:
            issues.append(
                error(csv_name, where, f"잘못된 포지션 {bad} (허용: {', '.join(POSITIONS_2K)})")
            )
            continue
        if secondary and not primary:
            issues.append(error(csv_name, where, "secondary 만 있고 primary 가 없습니다"))
            continue
        if secondary and secondary == primary:
            issues.append(error(csv_name, where, "primary 와 secondary 가 같습니다"))
            continue
        out[pid] = [v for v in (primary, secondary) if v]
    return out, issues


def import_csv(
    data_root: Path, csv_path: Path, apply: bool = True
) -> tuple[list[PositionChange], list[Issue]]:
    """CSV 의 포지션을 팀 파일에 반영한다. 오류가 하나라도 있으면 아무것도 쓰지 않는다."""
    csv_name = Path(csv_path).name
    try:
        text = Path(csv_path).read_text("utf-8-sig")
    except UnicodeDecodeError:
        return [], [error(csv_name, "", "UTF-8 로 읽을 수 없습니다 (엑셀에서 'CSV UTF-8' 로 저장)")]
    wanted, issues = parse_csv(text, csv_name)

    ds, load_issues = load_dataset(data_root)
    issues += [i for i in load_issues if i.file.startswith(TEAMS_DIR)]
    where_is = {p["id"]: (f, p) for f, t in ds.teams.items() for p in t["players"]}
    for pid in wanted:
        if pid not in where_is:
            issues.append(error(csv_name, "", f"존재하지 않는 선수 id '{pid}'"))
    if any(i.level == "error" for i in issues):
        return [], issues

    changes: list[PositionChange] = []
    touched: set[str] = set()
    for pid, new in wanted.items():
        file, p = where_is[pid]
        old = p.get("positions") or []
        if old != new:
            changes.append(PositionChange(file, pid, p["name_ko"], tuple(old), tuple(new)))
            p["positions"] = new
            touched.add(file)

    if apply:
        for file in sorted(touched):
            text = json.dumps(ds.teams[file], ensure_ascii=False, indent=2) + "\n"
            (Path(data_root) / file).write_text(text, "utf-8", newline="\n")
    return changes, issues
