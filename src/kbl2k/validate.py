"""데이터셋 전체 검증: 스키마 검증 + 파일 간 의미 검증."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from .dataset import MAPPING_FILE, RULES_FILE, SOURCES_FILE, Dataset, load_dataset
from .issues import Issue, error, warning
from .mapping import check_mapping
from .schema import schema_issues

EXPECTED_SEASON = "2026-27"


def validate_dataset(root: Path) -> list[Issue]:
    ds, issues = load_dataset(root)
    ok_teams = _schema_pass(ds, issues)
    source_ids = _check_sources(ds, issues)
    if source_ids is not None:
        for file, team in ok_teams.items():
            issues += check_team(team, file, source_ids)
    issues += _check_cross_team(ok_teams)
    if ds.mapping is not None and _no_errors_for(issues, MAPPING_FILE):
        issues += check_mapping(ds.mapping, list(ok_teams.values()), MAPPING_FILE)
    if ds.rules is not None and _no_errors_for(issues, RULES_FILE):
        issues += check_rules(ds.rules, RULES_FILE)
    return sorted(set(issues))


def _no_errors_for(issues: list[Issue], file: str) -> bool:
    return not any(i.file == file and i.level == "error" for i in issues)


def _schema_pass(ds: Dataset, issues: list[Issue]) -> dict[str, Any]:
    if ds.sources is not None:
        issues += schema_issues("sources", ds.sources, SOURCES_FILE)
    if ds.mapping is not None:
        issues += schema_issues("asset_mapping", ds.mapping, MAPPING_FILE)
    if ds.rules is not None:
        issues += schema_issues("rating_rules", ds.rules, RULES_FILE)
    ok: dict[str, Any] = {}
    for file, team in ds.teams.items():
        errs = schema_issues("team", team, file)
        issues += errs
        if not errs:
            ok[file] = team
    return ok


def _check_sources(ds: Dataset, issues: list[Issue]) -> set[str] | None:
    if ds.sources is None or not _no_errors_for(issues, SOURCES_FILE):
        return None
    ids = [s["id"] for s in ds.sources["sources"]]
    for sid, n in Counter(ids).items():
        if n > 1:
            issues.append(error(SOURCES_FILE, "$.sources", f"source id '{sid}' 중복 ({n}회)"))
    return set(ids)


def check_team(team: dict[str, Any], file: str, source_ids: set[str]) -> list[Issue]:
    """스키마를 통과한 팀 문서 한 개에 대한 의미 검증."""
    issues: list[Issue] = []
    issues += _check_refs(team["verification"]["sources"], source_ids, file, "$.verification")

    jerseys: Counter[int] = Counter()
    for i, p in enumerate(team["players"]):
        path = f"$.players[{i}]"
        if p["team_id"] != team["id"]:
            issues.append(
                error(file, f"{path}.team_id", f"'{p['team_id']}' ≠ 팀 id '{team['id']}'")
            )
        if p["jersey_number"] is not None:
            jerseys[p["jersey_number"]] += 1
        issues += _check_refs(
            p["verification"]["sources"], source_ids, file, f"{path}.verification"
        )
        for season, line in p.get("stats", {}).items():
            if line["source_id"] not in source_ids:
                issues.append(
                    error(
                        file, f"{path}.stats.{season}", f"알 수 없는 source '{line['source_id']}'"
                    )
                )
        if p["verification"]["status"] == "verified":
            # positions(2K 포지션)는 모드 설계 결정이므로 사실 확인 대상에서 제외
            missing = [k for k in ("jersey_number", "height_cm", "player_type") if p[k] is None]
            if missing:
                issues.append(
                    warning(file, path, f"verified 선수에 비어있는 필드: {', '.join(missing)}")
                )
    for num, n in jerseys.items():
        if n > 1:
            issues.append(error(file, "$.players", f"등번호 {num} 중복 ({n}명)"))
    return issues


def _check_refs(refs: list[str], source_ids: set[str], file: str, path: str) -> list[Issue]:
    return [error(file, path, f"알 수 없는 source '{r}'") for r in refs if r not in source_ids]


def _check_cross_team(teams: dict[str, Any]) -> list[Issue]:
    issues: list[Issue] = []
    team_ids: dict[str, str] = {}
    player_ids: dict[str, str] = {}
    for file, team in teams.items():
        if team["id"] in team_ids:
            issues.append(
                error(file, "$.id", f"팀 id '{team['id']}' 가 {team_ids[team['id']]} 와 중복")
            )
        team_ids.setdefault(team["id"], file)
        for i, p in enumerate(team["players"]):
            if p["id"] in player_ids:
                issues.append(
                    error(
                        file,
                        f"$.players[{i}].id",
                        f"선수 id '{p['id']}' 가 {player_ids[p['id']]} 와 중복",
                    )
                )
            player_ids.setdefault(p["id"], file)
    return issues


def check_rules(rules: dict[str, Any], file: str) -> list[Issue]:
    issues: list[Issue] = []
    if rules["clamp"]["min"] > rules["clamp"]["max"]:
        issues.append(error(file, "$.clamp", "min 이 max 보다 큽니다"))
    if rules.get("provisional"):
        issues.append(
            warning(file, "$.provisional", "잠정 규칙 — 평균/표준편차 보정(calibrate) 필요")
        )
    return issues
