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
    _edit_team(dataset, lambda t: t["players"][0]["stats"]["2025-26"].update(source_id="nope"))
    assert any("stats.2025-26" in e.path for e in errors(dataset))


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
