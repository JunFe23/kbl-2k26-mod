"""KBL 기록 → NBA 2K26 능력치 산정.

각 능력치 = clamp(base + spread * z + league_offset + position_bonus)
  z = Σ(weight_i * z_i) / Σ|weight_i|   (값이 있는 구성요소만)
  z_i = clip((x - mean) / sd, ±z_cap) × 표본 축소 계수

표본 축소:
  - 기록 지표: 출전 경기 gp < min_games 이면 gp/min_games 배 (평균 쪽으로 회귀)
  - volume 지정 지표(예: 3P%): 시도 수 / full 배 (최대 1)
  - 신장·체중은 축소하지 않음

모든 계수는 data/rules/rating_rules.json 에 있으며 코드는 순수 함수로만 구성한다.
"""

from __future__ import annotations

import copy
import math
import statistics
from dataclasses import dataclass, field
from typing import Any, Literal

BODY_INPUTS = frozenset({"height_cm", "weight_kg"})

Source = Literal["computed", "override", "default"]


@dataclass(frozen=True)
class AttributeResult:
    value: int
    source: Source
    z: float | None = None
    inputs_used: tuple[str, ...] = ()


@dataclass(frozen=True)
class PlayerRatings:
    player_id: str
    name_ko: str
    positions: tuple[str, ...]
    season: str | None
    games_factor: float
    ovr: int
    attributes: dict[str, AttributeResult] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "player_id": self.player_id,
            "name_ko": self.name_ko,
            "positions": list(self.positions),
            "season": self.season,
            "games_factor": round(self.games_factor, 3),
            "ovr": self.ovr,
            "attributes": {k: v.value for k, v in self.attributes.items()},
            "attribute_sources": {k: v.source for k, v in self.attributes.items()},
        }


def round_half_up(x: float) -> int:
    return math.floor(x + 0.5)


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def pick_stat_line(
    player: dict[str, Any], season: str | None = None
) -> tuple[str | None, dict[str, Any] | None]:
    stats = player.get("stats") or {}
    if season is not None:
        return (season, stats[season]) if season in stats else (None, None)
    if not stats:
        return None, None
    latest = max(stats)  # "YYYY-YY" 문자열은 사전순 = 시간순
    return latest, stats[latest]


def player_inputs(player: dict[str, Any], line: dict[str, Any] | None) -> dict[str, float | None]:
    inputs: dict[str, float | None] = {}
    if line:
        inputs.update({k: v for k, v in line.items() if k not in ("source_id", "gp")})
    inputs["height_cm"] = player.get("height_cm")
    inputs["weight_kg"] = player.get("weight_kg")
    return inputs


def games_factor(line: dict[str, Any] | None, min_games: int) -> float:
    if not line or line.get("gp") is None:
        return 0.0
    return min(1.0, line["gp"] / min_games)


def component_z(
    comp: dict[str, Any], inputs: dict[str, float | None], z_cap: float, gfactor: float
) -> float | None:
    """구성요소 하나의 (축소 적용된) z. 입력값이 없으면 None."""
    x = inputs.get(comp["input"])
    if x is None:
        return None
    z = clamp((x - comp["mean"]) / comp["sd"], -z_cap, z_cap)
    if comp["input"] not in BODY_INPUTS:
        z *= gfactor
    vol = comp.get("volume")
    if vol is not None:
        v = inputs.get(vol["input"])
        z *= 0.0 if v is None else min(1.0, v / vol["full"])
    return z


def position_bonus(rule: dict[str, Any], positions: tuple[str, ...]) -> float:
    if not positions:
        return 0.0
    return rule.get("position_bonus", {}).get(positions[0], 0.0)


def compute_attribute(
    rule: dict[str, Any],
    inputs: dict[str, float | None],
    positions: tuple[str, ...],
    rules: dict[str, Any],
    gfactor: float,
) -> AttributeResult:
    lo, hi = rules["clamp"]["min"], rules["clamp"]["max"]
    bonus = position_bonus(rule, positions)
    num = den = 0.0
    used: list[str] = []
    for comp in rule["components"]:
        z = component_z(comp, inputs, rules["z_cap"], gfactor)
        if z is None:
            continue
        num += comp["weight"] * z
        den += abs(comp["weight"])
        used.append(comp["input"])

    if den == 0:
        value = rules["base"] + rules["league_offset"] + bonus
        return AttributeResult(round_half_up(clamp(value, lo, hi)), "default")

    z = num / den
    value = rules["base"] + rules["spread"] * z + rules["league_offset"] + bonus
    return AttributeResult(
        round_half_up(clamp(value, lo, hi)), "computed", round(z, 4), tuple(used)
    )


def compute_ovr(
    attributes: dict[str, int], positions: tuple[str, ...], rules: dict[str, Any]
) -> int:
    ovr_rules = rules["ovr"]
    weights = ovr_rules.get(positions[0]) if positions else None
    weights = weights or ovr_rules["default"]
    pairs = [(attributes[a], w) for a, w in weights.items() if a in attributes]
    if not pairs:
        return rules["clamp"]["min"]
    value = sum(v * w for v, w in pairs) / sum(w for _, w in pairs)
    return round_half_up(clamp(value, rules["clamp"]["min"], rules["clamp"]["max"]))


def rate_player(
    player: dict[str, Any], rules: dict[str, Any], season: str | None = None
) -> PlayerRatings:
    season_used, line = pick_stat_line(player, season or rules.get("stats_season"))
    if line is None and season is None and rules.get("stats_season"):
        # 기준 시즌 기록이 없으면 가장 최근 시즌 기록 사용
        season_used, line = pick_stat_line(player)
    inputs = player_inputs(player, line)
    gfactor = games_factor(line, rules["min_games"])
    positions = tuple(player.get("positions") or ())
    overrides = player.get("ratings_override") or {}

    results: dict[str, AttributeResult] = {}
    for name, rule in rules["attributes"].items():
        if name in overrides:
            results[name] = AttributeResult(overrides[name], "override")
        else:
            results[name] = compute_attribute(rule, inputs, positions, rules, gfactor)

    ovr = compute_ovr({k: v.value for k, v in results.items()}, positions, rules)
    return PlayerRatings(
        player_id=player["id"],
        name_ko=player["name_ko"],
        positions=positions,
        season=season_used,
        games_factor=gfactor,
        ovr=ovr,
        attributes=results,
    )


def rate_team(
    team: dict[str, Any], rules: dict[str, Any], season: str | None = None
) -> list[PlayerRatings]:
    return [rate_player(p, rules, season) for p in team["players"]]


def calibrate(
    players: list[dict[str, Any]], rules: dict[str, Any], season: str, min_samples: int = 10
) -> tuple[dict[str, Any], dict[str, int]]:
    """주어진 선수 집단의 시즌 기록으로 각 구성요소의 mean/sd 를 다시 계산한다.

    min_games 이상 출전한 선수만 표본으로 쓰며, 표본이 min_samples 미만인 입력은
    기존 값을 유지한다. (새 규칙, 입력별 표본 수)를 반환한다.
    """
    samples: dict[str, list[float]] = {}
    for p in players:
        line = (p.get("stats") or {}).get(season)
        if not line or (line.get("gp") or 0) < rules["min_games"]:
            continue
        for k, v in player_inputs(p, line).items():
            if v is not None:
                samples.setdefault(k, []).append(float(v))

    new = copy.deepcopy(rules)
    counts = {k: len(v) for k, v in samples.items()}
    for rule in new["attributes"].values():
        for comp in rule["components"]:
            xs = samples.get(comp["input"], [])
            if len(xs) >= min_samples:
                sd = statistics.pstdev(xs)
                if sd > 0:
                    comp["mean"] = round(statistics.fmean(xs), 4)
                    comp["sd"] = round(sd, 4)
    new["stats_season"] = season
    new["provisional"] = False
    return new, counts
