import copy

import pytest
from conftest import CENTER, GUARD, make_player

from kbl2k.ratings import (
    calibrate,
    component_z,
    compute_ovr,
    games_factor,
    pick_stat_line,
    rate_player,
    round_half_up,
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
    assert all(a.source == "default" for a in r.attributes.values())
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
    hi["stats"]["2025-26"]["spg"] = 50
    lo = copy.deepcopy(GUARD)
    lo["stats"]["2025-26"]["spg"] = 0
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
    small["stats"]["2025-26"]["gp"] = 5
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


def test_pick_stat_line():
    p = make_player(
        "test-x1",
        stats={
            "2024-25": {"source_id": "s", "gp": 1},
            "2025-26": {"source_id": "s", "gp": 2},
        },
    )
    assert pick_stat_line(p)[0] == "2025-26"
    assert pick_stat_line(p, "2024-25")[1]["gp"] == 1
    assert pick_stat_line(p, "2019-20") == (None, None)


def test_falls_back_to_latest_when_rules_season_missing(rules):
    p = copy.deepcopy(GUARD)
    p["stats"] = {"2024-25": p["stats"]["2025-26"]}
    assert rate_player(p, rules).season == "2024-25"
    assert rate_player(p, rules, season="2025-26").season is None


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
    players = []
    for i in range(12):
        p = copy.deepcopy(GUARD)
        p["id"] = f"test-p{i}"
        p["height_cm"] = 180 + i
        players.append(p)
    new, counts = calibrate(players, rules, "2025-26", min_samples=10)
    assert counts["height_cm"] == 12
    speed = new["attributes"]["Speed"]["components"][0]
    assert speed["mean"] == pytest.approx(185.5)
    # 모든 선수 spg 동일 → sd 0 → 기존 값 유지
    steal = new["attributes"]["Steal"]["components"][0]
    assert steal["mean"] == rules["attributes"]["Steal"]["components"][0]["mean"]
    assert new["provisional"] is False
    assert schema_issues("rating_rules", new, "f") == []
    assert rules["provisional"] is True  # 원본 불변


def test_calibrate_ignores_small_samples(rules):
    new, counts = calibrate([GUARD, CENTER], rules, "2025-26", min_samples=10)
    assert new["attributes"] == rules["attributes"]
