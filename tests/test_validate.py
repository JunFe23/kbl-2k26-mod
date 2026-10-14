from pathlib import Path

from conftest import make_player, read, write

from kbl2k.issues import has_errors
from kbl2k.validate import validate_dataset

REPO_DATA = Path(__file__).resolve().parents[1] / "data"


def errors(root):
    return [i for i in validate_dataset(root) if i.level == "error"]


def test_fixture_dataset_is_clean(dataset):
    assert errors(dataset) == []


def test_repo_data_is_valid():
    assert errors(REPO_DATA) == []


def test_missing_dir():
    assert has_errors(validate_dataset(Path("does-not-exist")))


def test_broken_json_reported(dataset):
    (dataset / "teams" / "test_a.json").write_text("{bad", "utf-8")
    errs = errors(dataset)
    assert any("JSON 파싱 실패" in e.message for e in errs)


def _edit_team(dataset, fn):
    path = dataset / "teams" / "test_a.json"
    team = read(path)
    fn(team)
    write(path, team)


def test_duplicate_jersey(dataset):
    _edit_team(dataset, lambda t: t["players"][1].update(jersey_number=3))
    assert any("등번호 3 중복" in e.message for e in errors(dataset))


def test_team_id_mismatch(dataset):
    _edit_team(dataset, lambda t: t["players"][0].update(team_id="other"))
    assert any(e.path == "$.players[0].team_id" for e in errors(dataset))


def test_unknown_source(dataset):
    _edit_team(dataset, lambda t: t["players"][0]["verification"].update(sources=["nope"]))
    assert any("nope" in e.message for e in errors(dataset))


def test_unknown_stats_source(dataset):
    _edit_team(dataset, lambda t: t["players"][0]["stats"][0].update(source_id="nope"))
    assert any("stats[0]" in e.path for e in errors(dataset))


def test_duplicate_player_across_teams(dataset):
    other = read(dataset / "teams" / "test_a.json")
    other["id"] = "test-b"
    other["players"] = [make_player("test-g1", team_id="test-b")]
    write(dataset / "teams" / "test_b.json", other)
    assert any("선수 id 'test-g1'" in e.message for e in errors(dataset))


def test_duplicate_team_id(dataset):
    other = read(dataset / "teams" / "test_a.json")
    other["players"] = []
    write(dataset / "teams" / "test_z.json", other)
    assert any("팀 id 'test-a'" in e.message for e in errors(dataset))


def test_duplicate_source_id(dataset):
    s = read(dataset / "sources.json")
    s["sources"].append(dict(s["sources"][0]))
    write(dataset / "sources.json", s)
    assert any("중복" in e.message for e in errors(dataset))


def test_verified_player_missing_fields_is_warning(dataset):
    _edit_team(dataset, lambda t: t["players"][0].update(height_cm=None))
    issues = validate_dataset(dataset)
    assert not has_errors(issues)
    assert any(i.level == "warning" and "height_cm" in i.message for i in issues)


def test_provisional_rules_warns(dataset):
    assert any(
        i.file.endswith("rating_rules.json") and i.level == "warning"
        for i in validate_dataset(dataset)
    )


def test_rules_clamp_order(dataset):
    path = dataset / "rules" / "rating_rules.json"
    r = read(path)
    r["clamp"] = {"min": 90, "max": 40}
    write(path, r)
    assert any("min 이 max" in e.message for e in errors(dataset))


def _set_status(dataset, injured_state="injured", **replacement):
    def fn(t):
        t["players"][1]["roster_status"] = {"state": injured_state}
        t["players"][0]["roster_status"] = {"state": "replacement", **replacement}

    _edit_team(dataset, fn)


def test_replacement_of_injured_player_ok(dataset):
    _set_status(dataset, replaces="test-c1")
    assert validate_dataset(dataset) == [
        i for i in validate_dataset(dataset) if i.level == "warning"
    ]
    assert not any("roster_status" in i.path for i in validate_dataset(dataset))


def test_replacement_requires_replaces(dataset):
    _set_status(dataset)
    assert any("roster_status" in e.path for e in errors(dataset))


def test_replaces_unknown_player(dataset):
    _set_status(dataset, replaces="ghost")
    assert any("같은 팀에 없는" in e.message for e in errors(dataset))


def test_replaces_self(dataset):
    _set_status(dataset, replaces="test-g1")
    assert any("자기 자신" in e.message for e in errors(dataset))


def test_replaces_non_injured_warns(dataset):
    _set_status(dataset, injured_state="active", replaces="test-c1")
    issues = validate_dataset(dataset)
    assert not has_errors(issues)
    assert any("injured 상태가 아님" in i.message for i in issues)


def test_replaces_only_for_replacement(dataset):
    _edit_team(
        dataset,
        lambda t: t["players"][0].update(roster_status={"state": "injured", "replaces": "test-c1"}),
    )
    assert errors(dataset)


def _edit_sources(dataset, **kw):
    s = read(dataset / "sources.json")
    s["sources"][0].update(kw)
    write(dataset / "sources.json", s)


def test_manual_source_without_url_ok(dataset):
    _edit_sources(dataset, url=None, official=False)
    assert errors(dataset) == []


def test_official_source_needs_url(dataset):
    _edit_sources(dataset, url=None, official=True)
    assert any(e.file == "sources.json" for e in errors(dataset))


def test_repo_roster_status_consistent():
    team = read(REPO_DATA / "teams" / "anyang_kgc.json")
    by_name = {p["name_ko"]: p for p in team["players"]}
    assert by_name["라숀 토마스"]["roster_status"]["state"] == "injured"
    assert by_name["데이본 리드"]["roster_status"]["replaces"] == by_name["라숀 토마스"]["id"]
    sk = {p["name_ko"]: p for p in read(REPO_DATA / "teams" / "seoul_sk.json")["players"]}
    assert sk["프레디"]["nationality"] == "CD"


def test_rating_basis_must_match_a_stat_line(dataset):
    _edit_team(
        dataset,
        lambda t: t["players"][0].update(rating_basis={"season": "2025-26", "league": "LBA"}),
    )
    assert any("rating_basis" in e.path for e in errors(dataset))


def test_unknown_league_warns(dataset):
    _edit_team(dataset, lambda t: t["players"][0]["stats"][0].update(league="Mars League"))
    issues = validate_dataset(dataset)
    assert not has_errors(issues)
    assert any("Mars League" in i.message for i in issues)


def test_known_foreign_league_no_warning(dataset):
    path = dataset / "rules" / "rating_rules.json"
    r = read(path)
    r["league_offsets"] = {"LBA": 3}
    write(path, r)
    _edit_team(dataset, lambda t: t["players"][0]["stats"][0].update(league="LBA"))
    assert not any("LBA" in i.message for i in validate_dataset(dataset))


def test_duplicate_stat_line(dataset):
    _edit_team(
        dataset, lambda t: t["players"][0]["stats"].append(dict(t["players"][0]["stats"][0]))
    )
    assert any("중복" in e.message for e in errors(dataset))


def test_stat_line_requires_season_and_league(dataset):
    _edit_team(dataset, lambda t: t["players"][0]["stats"][0].pop("league"))
    assert errors(dataset)


def test_stat_line_rejects_unknown_field(dataset):
    _edit_team(dataset, lambda t: t["players"][0]["stats"][0].update(per=20))
    assert errors(dataset)
