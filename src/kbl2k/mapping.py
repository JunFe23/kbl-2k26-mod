"""선수 얼굴 / 팀 유니폼·코트·로고 에셋 ID 매핑.

2K26 의 실제 파일명·ID 규칙은 아직 검증되지 않았으므로 여기서는 형식을 강제하지 않고
참조 무결성(대상 존재, 중복, ID 충돌)과 진행 현황만 관리한다.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from .issues import Issue, error, warning

REQUIRED_PLAYER_ASSETS = ("face",)
REQUIRED_TEAM_ASSETS = ("uniform_home", "uniform_away", "court", "logo")


@dataclass(frozen=True)
class CoverageRow:
    entity_type: str
    entity_id: str
    name: str
    asset_type: str
    status: str  # planned | in_progress | verified | missing


def known_entities(teams: list[dict[str, Any]]) -> dict[tuple[str, str], str]:
    out: dict[tuple[str, str], str] = {}
    for team in teams:
        out[("team", team["id"])] = team["name_ko"]
        for p in team.get("players", []):
            out[("player", p["id"])] = p["name_ko"]
    return out


def check_mapping(mapping: dict[str, Any], teams: list[dict[str, Any]], file: str) -> list[Issue]:
    issues: list[Issue] = []
    entities = known_entities(teams)
    seen: dict[tuple[str, str, str], int] = {}
    by_game_id: dict[tuple[str, int], list[int]] = defaultdict(list)
    by_file: dict[str, list[int]] = defaultdict(list)

    for i, e in enumerate(mapping.get("entries", [])):
        path = f"$.entries[{i}]"
        ent = (e["entity_type"], e["entity_id"])
        if ent not in entities:
            issues.append(error(file, path, f"존재하지 않는 {ent[0]} '{ent[1]}' 참조"))
        key = (*ent, e["asset_type"])
        if key in seen:
            issues.append(error(file, path, f"중복 매핑 {key} (entries[{seen[key]}] 와 중복)"))
        else:
            seen[key] = i
        if e["game_id"] is not None:
            by_game_id[(e["asset_type"], e["game_id"])].append(i)
        if e["file"]:
            by_file[e["file"].replace("\\", "/").lower()].append(i)

    for (asset_type, gid), idxs in by_game_id.items():
        if len(idxs) > 1:
            issues.append(
                error(file, "$.entries", f"{asset_type} game_id {gid} 를 여러 항목이 사용: {idxs}")
            )
    for fname, idxs in by_file.items():
        if len(idxs) > 1:
            issues.append(error(file, "$.entries", f"파일 '{fname}' 을 여러 항목이 사용: {idxs}"))

    if mapping.get("game_version") is None and any(
        e["status"] == "verified" for e in mapping.get("entries", [])
    ):
        issues.append(
            warning(file, "$.game_version", "verified 항목이 있으나 game_version 이 없음")
        )
    return issues


def coverage(mapping: dict[str, Any] | None, teams: list[dict[str, Any]]) -> list[CoverageRow]:
    status: dict[tuple[str, str, str], str] = {}
    for e in (mapping or {}).get("entries", []):
        status[(e["entity_type"], e["entity_id"], e["asset_type"])] = e["status"]

    rows: list[CoverageRow] = []
    for team in teams:
        for a in REQUIRED_TEAM_ASSETS:
            st = status.get(("team", team["id"], a), "missing")
            rows.append(CoverageRow("team", team["id"], team["name_ko"], a, st))
        for p in team.get("players", []):
            for a in REQUIRED_PLAYER_ASSETS:
                st = status.get(("player", p["id"], a), "missing")
                rows.append(CoverageRow("player", p["id"], p["name_ko"], a, st))
    return rows
