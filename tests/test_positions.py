import csv
import io

import pytest
from conftest import read

from kbl2k.cli import main
from kbl2k.positions import KBL_TO_2K, export_csv, import_csv, parse_csv, position_issues
from kbl2k.schema import schema_issues


def rows_of(text):
    return list(csv.DictReader(io.StringIO(text.lstrip("﻿"))))


def write_csv(path, rows):
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(rows)
    path.write_text(buf.getvalue(), "utf-8-sig")


def team_players(dataset):
    return {p["id"]: p for p in read(dataset / "teams" / "test_a.json")["players"]}


def test_kbl_map_covers_all_2k_positions():
    assert sorted(v for vs in KBL_TO_2K.values() for v in vs) == sorted(
        ["PG", "SG", "SF", "PF", "C"]
    )


def test_position_kbl_schema():
    from conftest import make_player

    assert schema_issues("player", make_player("test-x1", position_kbl="F"), "f") == []
    assert schema_issues("player", make_player("test-x1", position_kbl="PG"), "f")
    assert schema_issues("player", make_player("test-x1", positions=["PG", "SG", "SF"]), "f")


def test_position_mismatch_is_warning():
    p = {"position_kbl": "G", "positions": ["C"]}
    issues = position_issues(p, "f", "$")
    assert len(issues) == 1 and issues[0].level == "warning"
    assert position_issues({"position_kbl": "G", "positions": ["SG", "SF"]}, "f", "$") == []
    assert position_issues({"position_kbl": None, "positions": ["C"]}, "f", "$") == []


def test_export_has_suggestions_and_current_values(dataset):
    teams = [read(dataset / "teams" / "test_a.json")]
    rows = rows_of(export_csv(teams))
    g = next(r for r in rows if r["player_id"] == "test-g1")
    assert g["position_kbl"] == "G" and g["suggested"] == "PG/SG"
    assert g["primary"] == "PG" and g["secondary"] == ""


def test_import_round_trip(dataset, tmp_path):
    rows = rows_of(export_csv([read(dataset / "teams" / "test_a.json")]))
    for r in rows:
        if r["player_id"] == "test-g1":
            r["primary"], r["secondary"] = "sg", "PG"  # 소문자 허용
    path = tmp_path / "pos.csv"
    write_csv(path, rows)

    changes, issues = import_csv(dataset, path)
    assert issues == []
    assert [(c.player_id, c.old, c.new) for c in changes] == [("test-g1", ("PG",), ("SG", "PG"))]
    assert team_players(dataset)["test-g1"]["positions"] == ["SG", "PG"]


def test_import_dry_run_does_not_write(dataset, tmp_path):
    path = tmp_path / "pos.csv"
    write_csv(path, [{"player_id": "test-g1", "primary": "SF", "secondary": ""}])
    changes, _ = import_csv(dataset, path, apply=False)
    assert len(changes) == 1
    assert team_players(dataset)["test-g1"]["positions"] == ["PG"]


def test_import_blank_primary_clears(dataset, tmp_path):
    path = tmp_path / "pos.csv"
    write_csv(path, [{"player_id": "test-c1", "primary": "", "secondary": ""}])
    import_csv(dataset, path)
    assert team_players(dataset)["test-c1"]["positions"] == []


def test_rows_not_in_csv_untouched(dataset, tmp_path):
    path = tmp_path / "pos.csv"
    write_csv(path, [{"player_id": "test-g1", "primary": "SG", "secondary": ""}])
    import_csv(dataset, path)
    assert team_players(dataset)["test-c1"]["positions"] == ["C"]


@pytest.mark.parametrize(
    "row, needle",
    [
        ({"player_id": "test-g1", "primary": "G", "secondary": ""}, "잘못된 포지션"),
        ({"player_id": "test-g1", "primary": "", "secondary": "SG"}, "primary 가 없습니다"),
        ({"player_id": "test-g1", "primary": "PG", "secondary": "PG"}, "같습니다"),
        ({"player_id": "", "primary": "PG", "secondary": ""}, "비어 있습니다"),
    ],
)
def test_parse_errors(row, needle):
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(row))
    w.writeheader()
    w.writerow(row)
    _, issues = parse_csv(buf.getvalue(), "pos.csv")
    assert any(needle in i.message for i in issues)


def test_import_aborts_whole_file_on_any_error(dataset, tmp_path):
    path = tmp_path / "pos.csv"
    write_csv(path, [
        {"player_id": "test-g1", "primary": "SG", "secondary": ""},
        {"player_id": "ghost", "primary": "C", "secondary": ""},
    ])  # fmt: skip
    changes, issues = import_csv(dataset, path)
    assert changes == [] and any("ghost" in i.message for i in issues)
    assert team_players(dataset)["test-g1"]["positions"] == ["PG"]


def test_duplicate_rows_rejected():
    text = "player_id,primary,secondary\na,PG,\na,SG,\n"
    _, issues = parse_csv(text, "x.csv")
    assert any("여러 번" in i.message for i in issues)


def test_missing_columns():
    _, issues = parse_csv("id,pos\na,PG\n", "x.csv")
    assert issues and "열이 필요" in issues[0].message


def test_cli_export_import(capsys, dataset, tmp_path):
    out = tmp_path / "p.csv"
    assert main(["--data", str(dataset), "positions", "export", "-o", str(out)]) == 0
    assert out.read_bytes().startswith(b"\xef\xbb\xbf")  # 엑셀용 BOM
    rows = rows_of(out.read_text("utf-8-sig"))
    rows[0]["primary"] = "SF"
    write_csv(out, rows)
    code = main(["--data", str(dataset), "positions", "import", str(out)])
    text = capsys.readouterr().out
    assert code == 0 and "변경 1명" in text


def test_cli_import_error_exit(capsys, dataset, tmp_path):
    out = tmp_path / "p.csv"
    write_csv(out, [{"player_id": "test-g1", "primary": "X", "secondary": ""}])
    assert main(["--data", str(dataset), "positions", "import", str(out)]) == 1
    assert "취소" in capsys.readouterr().out


def test_written_file_still_valid(dataset, tmp_path):
    from kbl2k.validate import validate_dataset

    path = tmp_path / "pos.csv"
    write_csv(path, [{"player_id": "test-g1", "primary": "SG", "secondary": "PG"}])
    import_csv(dataset, path)
    assert [i for i in validate_dataset(dataset) if i.level == "error"] == []
    assert b"\r\n" not in (dataset / "teams" / "test_a.json").read_bytes()
