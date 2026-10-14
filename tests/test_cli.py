import json

from conftest import read, write

from kbl2k.cli import main


def run(capsys, *argv):
    code = main(list(argv))
    out = capsys.readouterr()
    return code, out.out, out.err


def test_validate_ok(capsys, dataset):
    code, out, _ = run(capsys, "--data", str(dataset), "validate", "-w")
    assert code == 0
    assert "오류 0건" in out
    assert "WARNING" in out


def test_validate_fails_on_error(capsys, dataset):
    path = dataset / "teams" / "test_a.json"
    t = read(path)
    t["season"] = "2025-26"
    write(path, t)
    code, out, _ = run(capsys, "--data", str(dataset), "validate")
    assert code == 1
    assert "ERROR" in out


def test_ratings_table(capsys, dataset):
    code, out, _ = run(capsys, "--data", str(dataset), "ratings", "test-a")
    assert code == 0
    assert "테스트 팀" in out and "OVR" in out


def test_ratings_json(capsys, dataset):
    code, out, _ = run(capsys, "--data", str(dataset), "ratings", "test_a", "--json")
    assert code == 0
    rows = json.loads(out)
    assert {r["player_id"] for r in rows} == {"test-g1", "test-c1"}
    assert len(rows[0]["attributes"]) == 22


def test_ratings_unknown_team(capsys, dataset):
    try:
        main(["--data", str(dataset), "ratings", "nope"])
    except SystemExit as e:
        assert "팀을 찾을 수 없습니다" in str(e.code)
    else:
        raise AssertionError


def test_ratings_refuses_invalid_data(capsys, dataset):
    (dataset / "sources.json").write_text("{", "utf-8")
    try:
        main(["--data", str(dataset), "ratings", "test-a"])
    except SystemExit as e:
        assert e.code == 1
    else:
        raise AssertionError


def test_mapping_summary(capsys, dataset):
    code, out, _ = run(capsys, "--data", str(dataset), "mapping", "-v")
    assert code == 0
    assert "face" in out and "planned 1" in out and "missing" in out


def test_calibrate_prints_rules(capsys, dataset):
    code, out, err = run(capsys, "--data", str(dataset), "calibrate", "2025-26")
    assert code == 0
    assert json.loads(out)["stats_season"] == "2025-26"
    assert "표본 수" in err


def test_backup_verify_restore_cycle(capsys, tmp_path):
    game = tmp_path / "game"
    game.mkdir()
    (game / "x.iff").write_bytes(b"orig")
    out_dir = tmp_path / "bk"
    code, out, _ = run(capsys, "backup", "--game-dir", str(game), "--out", str(out_dir), "x.iff")
    assert code == 0
    bdir = next(out_dir.iterdir())
    assert run(capsys, "verify-backup", str(bdir))[0] == 0

    (game / "x.iff").write_bytes(b"mod")
    code, out, _ = run(capsys, "restore", str(bdir), "--game-dir", str(game))
    assert code == 0 and "dry-run" in out
    assert (game / "x.iff").read_bytes() == b"mod"
    code, out, _ = run(capsys, "restore", str(bdir), "--game-dir", str(game), "--apply")
    assert code == 0 and (game / "x.iff").read_bytes() == b"orig"


def test_backup_error_exit_code(capsys, tmp_path):
    code, _, err = run(capsys, "backup", "--game-dir", str(tmp_path / "none"), "a")
    assert code == 1 and "백업 실패" in err
