from conftest import GUARD, make_team

from kbl2k.mapping import REQUIRED_TEAM_ASSETS, check_mapping, coverage

TEAMS = [make_team(players=[GUARD])]


def entry(**kw):
    e = {
        "entity_type": "player",
        "entity_id": "test-g1",
        "asset_type": "face",
        "game_id": None,
        "file": None,
        "status": "planned",
    }
    e.update(kw)
    return e


def mapping(*entries, version=None):
    return {"game": "NBA 2K26 PC (Steam)", "game_version": version, "entries": list(entries)}


def msgs(m):
    return [i.message for i in check_mapping(m, TEAMS, "f") if i.level == "error"]


def test_clean():
    assert (
        msgs(mapping(entry(), entry(entity_type="team", entity_id="test-a", asset_type="logo")))
        == []
    )


def test_unknown_entity():
    assert any("존재하지 않는" in m for m in msgs(mapping(entry(entity_id="ghost"))))


def test_duplicate_entry():
    assert any("중복 매핑" in m for m in msgs(mapping(entry(), entry())))


def test_game_id_conflict_same_asset_type():
    m = mapping(
        entry(game_id=7),
        entry(entity_type="team", entity_id="test-a", asset_type="logo", game_id=7),
    )
    assert msgs(m) == []  # 다른 asset_type 은 충돌 아님
    teams = [make_team(players=[GUARD, {**GUARD, "id": "test-g2"}])]
    m2 = mapping(entry(game_id=7), entry(entity_id="test-g2", game_id=7))
    assert any("game_id 7" in i.message for i in check_mapping(m2, teams, "f"))


def test_file_conflict_case_and_slash_insensitive():
    teams = [make_team(players=[GUARD, {**GUARD, "id": "test-g2"}])]
    m = mapping(entry(file="mods/a.iff"), entry(entity_id="test-g2", file="MODS\\A.iff"))
    assert any("여러 항목" in i.message for i in check_mapping(m, teams, "f"))


def test_verified_without_game_version_warns():
    m = mapping(entry(status="verified", game_id=1, tool="X 1.0"))
    issues = check_mapping(m, TEAMS, "f")
    assert any(i.level == "warning" for i in issues)
    assert not check_mapping({**m, "game_version": "1.4"}, TEAMS, "f")


def test_coverage_marks_missing():
    rows = coverage(mapping(entry(status="in_progress")), TEAMS)
    face = [r for r in rows if r.asset_type == "face"]
    assert face[0].status == "in_progress"
    team_rows = [r for r in rows if r.entity_type == "team"]
    assert {r.asset_type for r in team_rows} == set(REQUIRED_TEAM_ASSETS)
    assert all(r.status == "missing" for r in team_rows)


def test_coverage_none_mapping():
    assert all(r.status == "missing" for r in coverage(None, TEAMS))
