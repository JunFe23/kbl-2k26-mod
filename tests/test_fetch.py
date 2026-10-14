"""KBL API 변환·수집 로직 테스트 (네트워크 사용 안 함, 가짜 응답)."""

import pytest
from conftest import read, write

from kbl2k import kbl_api
from kbl2k.fetch import (
    HISTORY_SOURCE,
    build_league_doc,
    fetch_league,
    fetch_players,
    league_file,
    merge_kbl_lines,
)
from kbl2k.schema import schema_issues
from kbl2k.validate import validate_dataset

# records/player/general/traditional 응답 한 행 (시즌 합계)
LEAGUE_ROW = {
    "playerNo": "291248", "kname": "테스트", "ename": "TEST", "teamCode": "55",
    "seasonCode": 47, "gameCount": 50, "playSec": 30000.0, "score": 1158.0,
    "rb": 500.0, "oR": 150.0, "dR": 350.0, "aS": 200.0, "sT": 60.0, "bS": 25.0, "tO": 90.0,
    "fg": 400.0, "fgA": 700.0, "threep": 10.0, "threepA": 40.0,
    "fdg": 410.0, "fdgA": 740.0, "ft": 300.0, "ftA": 400.0, "totalCn": 1,
}  # fmt: skip

# players/categories/season 의 RegularSeasonRecords 한 행
HISTORY_ROW = {
    "seasonCode": "47", "teamCode": "55", "gameCount": 50, "sumPlaySec": 30000,
    "sumScore": 1158, "sumRb": 500, "sumOR": 150, "sumDR": 350, "sumAS": 200, "sumSt": 60,
    "sumBs": 25, "sumTo": 90, "sumFdg": 410, "sumFdgA": 740, "sumThreeP": 10,
    "sumThreePA": 40, "sumFt": 300, "sumFtA": 400,
}  # fmt: skip


@pytest.mark.parametrize(
    "season, code", [("2025-26", 47), ("2026-27", 49), ("2019-20", 35), ("2024-25", 45)]
)
def test_season_code_round_trip(season, code):
    assert kbl_api.season_code(season) == code
    assert kbl_api.code_to_season(code) == season


@pytest.mark.parametrize("bad", ["2025", "2025-27", "25-26", "1990-91"])
def test_season_code_rejects_bad_format(bad):
    with pytest.raises(ValueError):
        kbl_api.season_code(bad)


def test_even_code_is_d_league():
    with pytest.raises(ValueError, match="D리그"):
        kbl_api.code_to_season(48)


def test_league_row_conversion():
    s = kbl_api.league_row_to_stats(LEAGUE_ROW)
    assert s["gp"] == 50
    assert s["mpg"] == 10.0  # 30000초 / 50경기 / 60
    assert s["ppg"] == 23.16
    assert s["orpg"] == 3.0 and s["drpg"] == 7.0
    assert s["fg_pct"] == round(410 / 740, 4)  # 전체 야투 = fdg
    assert s["fg3_pct"] == 0.25 and s["fg3a_pg"] == 0.8
    assert s["ft_pct"] == 0.75 and s["fta_pg"] == 8.0


def test_zero_attempts_give_null_pct():
    s = kbl_api.league_row_to_stats({**LEAGUE_ROW, "threep": 0.0, "threepA": 0.0})
    assert s["fg3_pct"] is None and s["fg3a_pg"] == 0.0


def test_history_and_league_conversions_agree():
    a = kbl_api.league_row_to_stats(LEAGUE_ROW)
    b = kbl_api.history_row_to_stats(HISTORY_ROW)
    assert a == b


def test_history_to_lines_filters_and_labels():
    data = {
        "RegularSeasonRecords": [
            HISTORY_ROW,
            {**HISTORY_ROW, "seasonCode": "45"},
            {**HISTORY_ROW, "seasonCode": "48"},  # D리그 → 제외
        ]
    }
    lines = kbl_api.history_to_stat_lines(data, "src-x", {"55": "서울 SK 나이츠"}, {"2025-26"})
    assert len(lines) == 1
    ln = lines[0]
    assert (ln["season"], ln["league"], ln["team"], ln["source_id"]) == (
        "2025-26",
        "KBL",
        "서울 SK 나이츠",
        "src-x",
    )
    all_lines = kbl_api.history_to_stat_lines(data, "src-x")
    assert [x["season"] for x in all_lines] == ["2025-26", "2024-25"]
    assert all_lines[0]["team"] == "KBL 팀코드 55"


def test_history_handles_missing_records():
    assert kbl_api.history_to_stat_lines({}, "s") == []


def test_merge_keeps_foreign_and_other_seasons():
    existing = [
        {"season": "2025-26", "league": "B.League B1", "gp": 1},
        {"season": "2025-26", "league": "KBL", "gp": 1},
        {"season": "2020-21", "league": "KBL", "gp": 1},
    ]
    fresh = [{"season": "2025-26", "league": "KBL", "gp": 50}]
    merged = merge_kbl_lines(existing, fresh, {"2025-26"})
    assert {(m["season"], m["league"], m["gp"]) for m in merged} == {
        ("2025-26", "B.League B1", 1),
        ("2025-26", "KBL", 50),
        ("2020-21", "KBL", 1),
    }
    assert merged[0]["league"] == "KBL"  # 같은 시즌이면 KBL 먼저


def test_build_league_doc_is_schema_valid():
    doc = build_league_doc("2025-26", [LEAGUE_ROW], "2026-10-14")
    assert schema_issues("league_stats", doc, "f") == []
    assert doc["kbl_season_code"] == 47
    assert doc["players"][0]["kbl_player_id"] == "291248"


def test_fetch_league_writes_file_and_source(dataset):
    path, n = fetch_league(
        dataset, "2025-26", fetch=lambda s: [LEAGUE_ROW], fetch_bodies=dict, today="2026-10-14"
    )
    assert n == 1 and path == dataset / league_file("2025-26")
    ids = {s["id"] for s in read(dataset / "sources.json")["sources"]}
    assert "kbl-stats-2025-26" in ids
    assert [i for i in validate_dataset(dataset) if i.level == "error"] == []


def test_fetch_league_refreshes_existing_source_date(dataset):
    fetch_league(
        dataset, "2025-26", fetch=lambda s: [LEAGUE_ROW], fetch_bodies=dict, today="2026-10-14"
    )
    fetch_league(
        dataset, "2025-26", fetch=lambda s: [LEAGUE_ROW], fetch_bodies=dict, today="2026-11-01"
    )
    srcs = [s for s in read(dataset / "sources.json")["sources"] if s["id"] == "kbl-stats-2025-26"]
    assert len(srcs) == 1 and srcs[0]["retrieved_at"] == "2026-11-01"


def test_invalid_league_file_reported(dataset):
    fetch_league(
        dataset, "2025-26", fetch=lambda s: [LEAGUE_ROW], fetch_bodies=dict, today="2026-10-14"
    )
    path = dataset / league_file("2025-26")
    doc = read(path)
    doc["players"][0]["ppg"] = -1
    write(path, doc)
    assert any(i.file == league_file("2025-26") for i in validate_dataset(dataset))


def test_fetch_players_updates_only_players_with_kbl_id(dataset):
    path = dataset / "teams" / "test_a.json"
    team = read(path)
    team["players"][0]["kbl_player_id"] = "291248"
    write(path, team)

    calls = []

    def fake(pid):
        calls.append(pid)
        return {"RegularSeasonRecords": [HISTORY_ROW]}

    result = fetch_players(dataset, {"2025-26"}, fetch=fake, delay=0, log=lambda m: None)
    assert calls == ["291248"]
    assert result == {"test-g1": 1}
    p = read(path)["players"][0]
    kbl = [ln for ln in p["stats"] if ln["source_id"] == HISTORY_SOURCE]
    assert len(kbl) == 1 and kbl[0]["ppg"] == 23.16
    assert [i for i in validate_dataset(dataset) if i.level == "error"] == []


def test_body_from_list_row_zero_is_none():
    assert kbl_api.body_from_list_row({"pHeight": "199.0", "pWeight": 118}) == {
        "height_cm": 199.0,
        "weight_kg": 118.0,
    }
    assert kbl_api.body_from_list_row({"pHeight": 0, "pWeight": None}) == {
        "height_cm": None,
        "weight_kg": None,
    }


def test_league_doc_joins_body_info():
    bodies = {"291248": {"height_cm": 199.0, "weight_kg": 118.0}}
    doc = build_league_doc("2025-26", [LEAGUE_ROW, {**LEAGUE_ROW, "playerNo": "1"}], "d", bodies)
    by = {p["kbl_player_id"]: p for p in doc["players"]}
    assert by["291248"]["height_cm"] == 199.0
    assert by["1"]["height_cm"] is None
    assert schema_issues("league_stats", {**doc, "retrieved_at": "2026-10-14"}, "f") == []
