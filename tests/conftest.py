"""테스트용 가상 데이터셋. 실존 선수 정보가 아님."""

from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
REAL_RULES = REPO / "data" / "rules" / "rating_rules.json"


def make_player(pid: str, team_id: str = "test-a", **kw) -> dict:
    p = {
        "id": pid,
        "name_ko": f"테스트{pid[-1]}",
        "name_en": None,
        "team_id": team_id,
        "jersey_number": None,
        "position_kbl": None,
        "positions": [],
        "height_cm": None,
        "weight_kg": None,
        "birth_date": None,
        "nationality": None,
        "player_type": None,
        "verification": {"status": "unverified", "sources": [], "checked_at": None},
    }
    p.update(kw)
    return p


def make_team(tid: str = "test-a", players: list | None = None, **kw) -> dict:
    t = {
        "id": tid,
        "name_ko": "테스트 팀",
        "name_en": "Test Team",
        "abbreviation": "TST",
        "city": None,
        "arena": None,
        "head_coach": None,
        "season": "2026-27",
        "nba_slot": None,
        "verification": {"status": "verified", "sources": ["src-a"], "checked_at": "2026-10-14"},
        "players": players or [],
    }
    t.update(kw)
    return t


GUARD = make_player(
    "test-g1",
    jersey_number=3,
    position_kbl="G",
    positions=["PG"],
    height_cm=180,
    weight_kg=75,
    player_type="domestic",
    nationality="KR",
    verification={"status": "verified", "sources": ["src-a"], "checked_at": "2026-10-14"},
    stats={
        "2025-26": {
            "source_id": "src-a",
            "gp": 54,
            "mpg": 32,
            "ppg": 15,
            "rpg": 3,
            "orpg": 0.5,
            "drpg": 2.5,
            "apg": 6,
            "spg": 1.5,
            "bpg": 0.1,
            "tpg": 2.2,
            "fg_pct": 0.44,
            "fg3_pct": 0.38,
            "ft_pct": 0.85,
            "fg3a_pg": 5,
            "fta_pg": 3,
        }
    },
)

CENTER = make_player(
    "test-c1",
    jersey_number=33,
    position_kbl="C",
    positions=["C"],
    height_cm=205,
    weight_kg=110,
    player_type="foreign",
    verification={"status": "verified", "sources": ["src-a"], "checked_at": "2026-10-14"},
    stats={
        "2025-26": {
            "source_id": "src-a",
            "gp": 50,
            "mpg": 30,
            "ppg": 20,
            "rpg": 11,
            "orpg": 3.5,
            "drpg": 7.5,
            "apg": 2,
            "spg": 0.7,
            "bpg": 1.5,
            "tpg": 2,
            "fg_pct": 0.56,
            "fg3_pct": None,
            "ft_pct": 0.62,
            "fg3a_pg": 0,
            "fta_pg": 5,
        }
    },
)


@pytest.fixture
def rules() -> dict:
    return json.loads(REAL_RULES.read_text("utf-8"))


@pytest.fixture
def dataset(tmp_path: Path) -> Path:
    """검증을 통과하는 최소 데이터셋 디렉터리."""
    root = tmp_path / "data"
    (root / "teams").mkdir(parents=True)
    (root / "rules").mkdir()
    (root / "mappings").mkdir()
    shutil.copy(REAL_RULES, root / "rules" / "rating_rules.json")
    write(
        root / "sources.json",
        {
            "sources": [
                {
                    "id": "src-a",
                    "title": "테스트 출처",
                    "url": "https://example.com/a",
                    "retrieved_at": "2026-10-14",
                }
            ]
        },
    )
    write(
        root / "teams" / "test_a.json",
        make_team(players=[copy.deepcopy(GUARD), copy.deepcopy(CENTER)]),
    )
    write(
        root / "mappings" / "assets.json",
        {
            "game": "NBA 2K26 PC (Steam)",
            "game_version": None,
            "entries": [
                {
                    "entity_type": "team",
                    "entity_id": "test-a",
                    "asset_type": "logo",
                    "game_id": None,
                    "file": None,
                    "status": "planned",
                },
                {
                    "entity_type": "player",
                    "entity_id": "test-g1",
                    "asset_type": "face",
                    "game_id": None,
                    "file": None,
                    "status": "planned",
                },
            ],
        },
    )
    return root


def write(path: Path, doc) -> None:
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), "utf-8")


def read(path: Path):
    return json.loads(path.read_text("utf-8"))
