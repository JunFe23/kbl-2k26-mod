import copy

import pytest
from conftest import CENTER, GUARD, make_player

from kbl2k.ratings import (
    AttributeResult,
    calibrate,
    component_z,
    compute_ovr,
    games_factor,
    league_adjustment,
    rate_player,
    round_half_up,
    select_stat_line,
)
from kbl2k.schema import attribute_names, schema_issues


def test_all_rule_attributes_are_known(rules):
    assert set(rules["attributes"]) <= set(attribute_names())


def test_rate_player_produces_all_attributes_in_range(rules):
    r = rate_player(GUARD, rules)
    assert set(r.attributes) == set(rules["attributes"])
    for a in r.attributes.values():
        assert 25 <= a.value <= 99
    assert 25 <= r.ovr <= 99
    assert r.season == "2025-26"


def test_guard_vs_center_profiles(rules):
    g = rate_player(GUARD, rules).attributes
    c = rate_player(CENTER, rules).attributes
    assert g["Three-Point Shot"].value > c["Three-Point Shot"].value
    assert g["Pass Accuracy"].value > c["Pass Accuracy"].value
    assert g["Speed"].value > c["Speed"].value
    assert c["Block"].value > g["Block"].value
    assert c["Defensive Rebound"].value > g["Defensive Rebound"].value
    assert c["Strength"].value > g["Strength"].value


def test_no_data_player_gets_defaults(rules):
    r = rate_player(make_player("test-x1"), rules)
    expected = rules["base"] + rules["league_offset"]
    assert all(a.source in ("default", "fixed") for a in r.attributes.values())
    assert r.attributes["Durability"].source == "fixed"
    assert r.attributes["Steal"].value == expected
    assert r.season is None and r.games_factor == 0


def test_override_wins_and_feeds_ovr(rules):
    p = copy.deepcopy(GUARD)
    p["ratings_override"] = {"Three-Point Shot": 95}
    r = rate_player(p, rules)
    assert r.attributes["Three-Point Shot"].value == 95
    assert r.attributes["Three-Point Shot"].source == "override"
    assert r.ovr >= rate_player(GUARD, rules).ovr


def test_clamp_upper_and_lower(rules):
    hi = copy.deepcopy(GUARD)
    hi["stats"][0]["spg"] = 50
    lo = copy.deepcopy(GUARD)
    lo["stats"][0]["spg"] = 0
    rules = copy.deepcopy(rules)
    rules["z_cap"] = 1000
    assert rate_player(hi, rules).attributes["Steal"].value == 99
    rules["league_offset"] = -200
    assert rate_player(lo, rules).attributes["Steal"].value == 25


def test_z_cap_limits_outlier(rules):
    comp = {"input": "spg", "mean": 0.7, "sd": 0.4, "weight": 1}
    assert component_z(comp, {"spg": 100}, 3, 1.0) == 3


def test_games_factor_shrinks_small_samples(rules):
    small = copy.deepcopy(GUARD)
    small["stats"][0]["gp"] = 5
    full = rate_player(GUARD, rules).attributes["Steal"].value
    shrunk = rate_player(small, rules).attributes["Steal"].value
    neutral = rules["base"] + rules["league_offset"]
    assert neutral <= shrunk < full


def test_games_factor_values():
    assert games_factor(None, 20) == 0
    assert games_factor({"gp": None}, 20) == 0
    assert games_factor({"gp": 10}, 20) == 0.5
    assert games_factor({"gp": 40}, 20) == 1


def test_body_inputs_not_shrunk():
    comp = {"input": "height_cm", "mean": 192, "sd": 8, "weight": 1}
    assert component_z(comp, {"height_cm": 200}, 3, 0.0) == 1


def test_volume_shrinks_low_attempt_percentage():
    comp = {
        "input": "fg3_pct",
        "mean": 0.32,
        "sd": 0.06,
        "weight": 1,
        "volume": {"input": "fg3a_pg", "full": 3},
    }
    full = component_z(comp, {"fg3_pct": 0.44, "fg3a_pg": 3}, 3, 1)
    low = component_z(comp, {"fg3_pct": 0.44, "fg3a_pg": 0.3}, 3, 1)
    none = component_z(comp, {"fg3_pct": 0.44, "fg3a_pg": None}, 3, 1)
    assert full == pytest.approx(2.0)
    assert low == pytest.approx(0.2)
    assert none == 0


def test_missing_component_renormalises(rules):
    # 센터는 fg3_pct 가 null → 3점 능력치는 시도 수 구성요소만으로 계산
    r = rate_player(CENTER, rules).attributes["Three-Point Shot"]
    assert r.source == "computed"
    assert r.inputs_used == ("fg3a_pg",)


def _ln(season, league="KBL", gp=30, **kw):
    return {"season": season, "league": league, "source_id": "s", "gp": gp, **kw}


def test_select_prefers_qualified_target_season(rules):
    rules = {**rules, "stats_season": "2025-26", "min_games": 20}
    p = make_player("test-x1", stats=[_ln("2024-25"), _ln("2025-26", gp=25), _ln("2023-24")])
    assert select_stat_line(p, rules)["season"] == "2025-26"


def test_select_skips_unqualified_target_for_recent_qualified(rules):
    rules = {**rules, "stats_season": "2025-26", "min_games": 20}
    p = make_player("test-x1", stats=[_ln("2025-26", gp=2), _ln("2023-24"), _ln("2024-25")])
    assert select_stat_line(p, rules)["season"] == "2024-25"


def test_select_falls_back_to_unqualified(rules):
    rules = {**rules, "min_games": 20}
    p = make_player("test-x1", stats=[_ln("2022-23", gp=3), _ln("2025-26", gp=2)])
    assert select_stat_line(p, rules)["season"] == "2025-26"


def test_select_prefers_kbl_then_regular_then_games(rules):
    rules = {**rules, "stats_season": "2025-26"}
    p = make_player("test-x1", stats=[
        _ln("2025-26", "B.League B1", gp=40),
        _ln("2025-26", "KBL", gp=30),
    ])  # fmt: skip
    assert select_stat_line(p, rules)["league"] == "KBL"
    p["stats"] = [
        _ln("2025-26", "LBA", gp=26, competition="regular_season"),
        _ln("2025-26", "FIBA Europe Cup", gp=30, competition="cup"),
    ]
    assert select_stat_line(p, rules)["league"] == "LBA"
    p["stats"] = [_ln("2025-26", "B.League B1", gp=9), _ln("2025-26", "B.League B2", gp=32)]
    assert select_stat_line(p, rules)["league"] == "B.League B2"


def test_rating_basis_overrides_auto_choice(rules):
    p = make_player(
        "test-x1",
        stats=[_ln("2025-26", "B.League B2", gp=32), _ln("2025-26", "B.League B1", gp=9)],
        rating_basis={"season": "2025-26", "league": "B.League B1"},
    )
    assert select_stat_line(p, rules)["gp"] == 9


def test_explicit_season(rules):
    p = make_player("test-x1", stats=[_ln("2024-25"), _ln("2025-26")])
    assert select_stat_line(p, rules, "2024-25")["season"] == "2024-25"
    assert select_stat_line(p, rules, "2019-20") is None
    assert rate_player(p, rules, season="2019-20").season is None


def test_no_stats_selects_none(rules):
    assert select_stat_line(make_player("test-x1"), rules) is None


def test_league_adjustment_values(rules):
    rules = {**rules, "league_offsets": {"LBA": 4}}
    assert league_adjustment(None, rules) == 0
    assert league_adjustment(_ln("2025-26"), rules) == 0
    assert league_adjustment(_ln("2025-26", "LBA"), rules) == 4
    assert league_adjustment(_ln("2025-26", "Unknown"), rules) == 0


def test_league_adjustment_applies_only_to_stat_part(rules):
    foreign = copy.deepcopy(GUARD)
    foreign["stats"][0]["league"] = "LBA"
    base = rate_player(foreign, rules).attributes
    boosted = rate_player(foreign, {**rules, "league_offsets": {"LBA": 10}}).attributes
    assert boosted["Steal"].value == min(99, base["Steal"].value + 10)  # 기록만 사용
    assert boosted["Speed"].value == base["Speed"].value  # 신장만 사용
    assert base["Block"].value < boosted["Block"].value < base["Block"].value + 10  # 혼합


def test_kbl_line_not_adjusted(rules):
    plain = rate_player(GUARD, rules)
    assert rate_player(GUARD, {**rules, "league_offsets": {"KBL": 10}}) == plain


def test_ovr_uses_position_weights(rules):
    attrs = {a: 50 for a in rules["attributes"]}
    attrs["Pass Accuracy"] = 99
    assert compute_ovr(attrs, ("PG",), rules) > compute_ovr(attrs, ("C",), rules)
    assert compute_ovr(attrs, (), rules) == compute_ovr(attrs, ("SF",), rules)


def test_round_half_up():
    assert round_half_up(62.5) == 63
    assert round_half_up(62.49) == 62


def test_deterministic(rules):
    assert rate_player(GUARD, rules) == rate_player(GUARD, rules)


def test_calibrate_updates_means_and_stays_schema_valid(rules):
    rows = [{**GUARD["stats"][0], "spg": 0.5 + i * 0.1, "height_cm": 180 + i} for i in range(12)]
    new, counts = calibrate(rows, rules, "2025-26", min_samples=10)
    assert counts["spg"] == 12 and counts["height_cm"] == 12
    steal = new["attributes"]["Steal"]["components"][0]
    assert steal["mean"] == pytest.approx(1.05)
    speed = new["attributes"]["Speed"]["components"][0]
    assert speed["mean"] == pytest.approx(185.5)
    # 모든 행 ppg 동일 → sd 0 → 기존 값 유지
    ppg = new["attributes"]["Driving Layup"]["components"][0]
    assert ppg["mean"] == rules["attributes"]["Driving Layup"]["components"][0]["mean"]
    assert new["stats_season"] == "2025-26"
    assert new["provisional"] == rules["provisional"]  # 잠정 표시는 유지
    assert schema_issues("rating_rules", new, "f") == []


def test_calibrate_ignores_small_samples_and_low_games(rules):
    rows = [{**GUARD["stats"][0], "spg": i, "gp": 5} for i in range(20)]
    new, counts = calibrate(rows, rules, "2025-26", min_samples=10)
    assert counts == {}
    assert new["attributes"] == rules["attributes"]


def test_fixed_attribute_ignores_stats_and_overridable(rules):
    r = rate_player(GUARD, rules)
    assert r.attributes["Durability"] == AttributeResult(
        rules["attributes"]["Durability"]["fixed"], "fixed"
    )
    p = copy.deepcopy(GUARD)
    p["ratings_override"] = {"Durability": 95}
    assert rate_player(p, rules).attributes["Durability"].value == 95


def test_fixed_rule_schema(rules):
    bad = copy.deepcopy(rules)
    bad["attributes"]["Durability"] = {
        "fixed": 80,
        "components": rules["attributes"]["Steal"]["components"],
    }
    assert schema_issues("rating_rules", bad, "f")
    bad["attributes"]["Durability"] = {"fixed": 120}
    assert schema_issues("rating_rules", bad, "f")


def test_extended_attributes_computed(rules):
    a = rate_player(GUARD, rules).attributes
    c = rate_player(CENTER, rules).attributes
    assert a["Pass IQ"].value > c["Pass IQ"].value
    assert c["Post Hook"].value > a["Post Hook"].value
    assert c["Draw Foul"].source == "computed"
