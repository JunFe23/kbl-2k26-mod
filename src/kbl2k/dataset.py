"""data/ 디렉터리 로딩.

레이아웃:
    data/sources.json
    data/teams/*.json
    data/mappings/assets.json
    data/rules/rating_rules.json
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .issues import Issue, error

SOURCES_FILE = "sources.json"
TEAMS_DIR = "teams"
MAPPING_FILE = "mappings/assets.json"
RULES_FILE = "rules/rating_rules.json"


class DataError(Exception):
    pass


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as e:
        raise DataError(f"파일 없음: {path}") from e
    except json.JSONDecodeError as e:
        raise DataError(f"JSON 파싱 실패: {path} (line {e.lineno}, col {e.colno}): {e.msg}") from e


@dataclass
class Dataset:
    root: Path
    sources: dict[str, Any] | None = None
    teams: dict[str, Any] = field(default_factory=dict)  # 상대 경로 → 팀 문서
    mapping: dict[str, Any] | None = None
    rules: dict[str, Any] | None = None

    def rel(self, path: Path) -> str:
        return path.relative_to(self.root).as_posix()


def load_dataset(root: Path) -> tuple[Dataset, list[Issue]]:
    root = Path(root)
    ds = Dataset(root=root)
    issues: list[Issue] = []

    if not root.is_dir():
        return ds, [error(str(root), "", "데이터 디렉터리가 없습니다")]

    def load(rel: str) -> Any:
        try:
            return read_json(root / rel)
        except DataError as e:
            issues.append(error(rel, "", str(e)))
            return None

    ds.sources = load(SOURCES_FILE)
    ds.mapping = load(MAPPING_FILE)
    ds.rules = load(RULES_FILE)

    team_dir = root / TEAMS_DIR
    team_files = sorted(team_dir.glob("*.json")) if team_dir.is_dir() else []
    if not team_files:
        issues.append(error(TEAMS_DIR, "", "팀 파일이 하나도 없습니다"))
    for path in team_files:
        doc = load(ds.rel(path))
        if doc is not None:
            ds.teams[ds.rel(path)] = doc

    return ds, issues
