import copy

import pytest
from conftest import GUARD, make_player, make_team

from kbl2k.schema import SCHEMA_NAMES, attribute_names, schema_issues, validator


@pytest.mark.parametrize("name", SCHEMA_NAMES)
def test_schemas_are_valid_draft_2020_12(name):
    validator(name)  # check_schema 통과 여부


def test_attribute_names_count():
    names = attribute_names()
    assert len(names) == 22
    assert "Three-Point Shot" in names


def test_minimal_unverified_player_ok():
    assert schema_issues("player", make_player("test-x1"), "f") == []


def test_full_player_ok():
    assert schema_issues("player", GUARD, "f") == []


@pytest.mark.parametrize(
    "patch, needle",
    [
        ({"jersey_number": 100}, "jersey_number"),
        ({"height_cm": 120}, "height_cm"),
        ({"positions": ["G"]}, "positions"),
        ({"nationality": "KOR"}, "nationality"),
        ({"birth_date": "1999-02-30"}, "birth_date"),
        ({"id": "Bad_ID"}, "id"),
        ({"player_type": "import"}, "player_type"),
        ({"kbl_player_id": "29a"}, "kbl_player_id"),
        ({"extra": 1}, "$"),
    ],
)
def test_invalid_player_fields(patch, needle):
    p = make_player("test-x1", **patch)
    issues = schema_issues("player", p, "f")
    assert issues, patch
    assert any(needle in i.path or needle in i.message for i in issues)


def test_missing_required_field_rejected():
    p = make_player("test-x1")
    del p["height_cm"]
    assert schema_issues("player", p, "f")


def test_verified_requires_source_and_date():
    p = make_player(
        "test-x1", verification={"status": "verified", "sources": [], "checked_at": None}
    )
    paths = {i.path for i in schema_issues("player", p, "f")}
    assert "$.verification.sources" in paths
    assert "$.verification.checked_at" in paths


def test_stat_line_pct_range():
    p = copy.deepcopy(GUARD)
    p["stats"][0]["fg3_pct"] = 38.0  # % 단위 실수
    assert any("fg3_pct" in i.path for i in schema_issues("player", p, "f"))


def test_override_attribute_name_and_range():
    p = make_player("test-x1", ratings_override={"Three-Point Shot": 80})
    assert schema_issues("player", p, "f") == []
    p["ratings_override"] = {"3PT": 80}
    assert schema_issues("player", p, "f")
    p["ratings_override"] = {"Three-Point Shot": 100}
    assert schema_issues("player", p, "f")


def test_team_season_must_be_2026_27():
    assert schema_issues("team", make_team(), "f") == []
    assert schema_issues("team", make_team(season="2025-26"), "f")


def test_team_player_errors_have_nested_path():
    t = make_team(players=[make_player("test-x1", jersey_number=-1)])
    assert any(i.path.startswith("$.players[0]") for i in schema_issues("team", t, "f"))


def _entry(**kw):
    e = {
        "entity_type": "player",
        "entity_id": "test-x1",
        "asset_type": "face",
        "game_id": None,
        "file": None,
        "status": "planned",
    }
    e.update(kw)
    return {"game": "NBA 2K26 PC (Steam)", "game_version": None, "entries": [e]}


def test_mapping_planned_entry_ok():
    assert schema_issues("asset_mapping", _entry(), "f") == []


def test_mapping_player_cannot_have_court():
    assert schema_issues("asset_mapping", _entry(asset_type="court"), "f")


def test_mapping_verified_needs_id_or_file_and_tool():
    assert schema_issues("asset_mapping", _entry(status="verified"), "f")
    assert schema_issues("asset_mapping", _entry(status="verified", game_id=5), "f")
    assert (
        schema_issues("asset_mapping", _entry(status="verified", game_id=5, tool="X 1.0"), "f")
        == []
    )


def test_real_rules_file_valid(rules):
    assert schema_issues("rating_rules", rules, "f") == []
