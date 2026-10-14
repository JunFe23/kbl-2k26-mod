"""경기 기록 → NBA 2K26 능력치 산정.

각 능력치 = clamp(base + spread * z + league_offset + 리그 보정 × 기록 비중 + position_bonus)
  z = Σ(weight_i * z_i) / Σ|weight_i|   (값이 있는 구성요소만)
  z_i = clip((x - mean) / sd, ±z_cap) × 표본 축소 계수

표본 축소:
  - 기록 지표: 출전 경기 gp < min_games 이면 gp/min_games 배 (평균 쪽으로 회귀)
  - volume 지정 지표(예: 3P%): 시도 수 / full 배 (최대 1)
  - 신장·체중은 축소하지 않음

리그 보정:
  - 기록이 KBL 이 아니면 rules.league_offsets[리그] 를 더한다.
  - 신장·체중만으로 정해지는 능력치에는 적용하지 않도록, 사용된 구성요소 중
    기록 지표의 가중치 비율만큼만 반영한다.

기록 선택 (rating_basis 가 없을 때):
  1) min_games 이상 출전한 기록 우선
  2) 그중 기준 시즌(stats_season) 우선, 다음은 최신 시즌
  3) 같은 조건이면 KBL > 해외, 정규시즌 > 기타, 경기 수 많은 순

모든 계수는 data/rules/rating_rules.json 에 있으며 코드는 순수 함수로만 구성한다.
"""

from __future__ import annotations

import copy
import math
import statistics
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, Literal

KBL = "KBL"
BODY_INPUTS = frozenset({"height_cm", "weight_kg"})
STAT_INPUTS = (
    "mpg", "ppg", "rpg", "orpg", "drpg", "apg", "spg", "bpg", "tpg",
    "fg_pct", "fg3_pct", "ft_pct", "fg3a_pg", "fta_pg",
)  # fmt: skip

Source = Literal["computed", "override", "default", "fixed"]


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
    league: str | None
    games_factor: float
    ovr: int
    attributes: dict[str, AttributeResult] = field(default_factory=dict)

    @property
    def basis(self) -> str:
        return f"{self.season} {self.league}" if self.season else "-"

    def as_dict(self) -> dict[str, Any]:
        return {
            "player_id": self.player_id,
            "name_ko": self.name_ko,
            "positions": list(self.positions),
            "season": self.season,
            "league": self.league,
            "games_factor": round(self.games_factor, 3),
            "ovr": self.ovr,
            "attributes": {k: v.value for k, v in self.attributes.items()},
            "attribute_sources": {k: v.source for k, v in self.attributes.items()},
        }


def round_half_up(x: float) -> int:
    return math.floor(x + 0.5)


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _rank(line: dict[str, Any], min_games: int, target: str | None) -> tuple:
    gp = line.get("gp") or 0
    return (
        gp >= min_games,
        line["season"] == target,
        line["season"],  # "YYYY-YY" 사전순 = 시간순
        line["league"] == KBL,
        line.get("competition", "regular_season") == "regular_season",
        gp,
    )


def select_stat_line(
    player: dict[str, Any], rules: dict[str, Any], season: str | None = None
) -> dict[str, Any] | None:
    lines: list[dict[str, Any]] = player.get("stats") or []
    min_games = rules["min_games"]
    if season is not None:
        lines = [ln for ln in lines if ln["season"] == season]
        return max(lines, key=lambda ln: _rank(ln, min_games, season), default=None)
    basis = player.get("rating_basis")
    if basis:
        lines = [
            ln for ln in lines
            if ln["season"] == basis["season"] and ln["league"] == basis["league"]
        ]  # fmt: skip
    return max(lines, key=lambda ln: _rank(ln, min_games, rules.get("stats_season")), default=None)


def player_inputs(player: dict[str, Any], line: dict[str, Any] | None) -> dict[str, float | None]:
    inputs: dict[str, float | None] = {k: (line or {}).get(k) for k in STAT_INPUTS}
    inputs["height_cm"] = player.get("height_cm")
    inputs["weight_kg"] = player.get("weight_kg")
    return inputs


def games_factor(line: dict[str, Any] | None, min_games: int) -> float:
    if not line or line.get("gp") is None:
        return 0.0
    return min(1.0, line["gp"] / min_games)


def league_adjustment(line: dict[str, Any] | None, rules: dict[str, Any]) -> float:
    if not line or line["league"] == KBL:
        return 0.0
    return rules.get("league_offsets", {}).get(line["league"], 0.0)


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
    league_adj: float = 0.0,
) -> AttributeResult:
    if "fixed" in rule:
        return AttributeResult(rule["fixed"], "fixed")
    lo, hi = rules["clamp"]["min"], rules["clamp"]["max"]
    bonus = position_bonus(rule, positions)
    num = den = stat_w = 0.0
    used: list[str] = []
    for comp in rule["components"]:
        z = component_z(comp, inputs, rules["z_cap"], gfactor)
        if z is None:
            continue
        num += comp["weight"] * z
        den += abs(comp["weight"])
        if comp["input"] not in BODY_INPUTS:
            stat_w += abs(comp["weight"])
        used.append(comp["input"])

    if den == 0:
        value = rules["base"] + rules["league_offset"] + bonus
        return AttributeResult(round_half_up(clamp(value, lo, hi)), "default")

    z = num / den
    value = (
        rules["base"]
        + rules["spread"] * z
        + rules["league_offset"]
        + league_adj * (stat_w / den)
        + bonus
    )
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
    line = select_stat_line(player, rules, season)
    inputs = player_inputs(player, line)
    gfactor = games_factor(line, rules["min_games"])
    adj = league_adjustment(line, rules)
    positions = tuple(player.get("positions") or ())
    overrides = player.get("ratings_override") or {}

    results: dict[str, AttributeResult] = {}
    for name, rule in rules["attributes"].items():
        if name in overrides:
            results[name] = AttributeResult(overrides[name], "override")
        else:
            results[name] = compute_attribute(rule, inputs, positions, rules, gfactor, adj)

    ovr = compute_ovr({k: v.value for k, v in results.items()}, positions, rules)
    return PlayerRatings(
        player_id=player["id"],
        name_ko=player["name_ko"],
        positions=positions,
        season=line["season"] if line else None,
        league=line["league"] if line else None,
        games_factor=gfactor,
        ovr=ovr,
        attributes=results,
    )


def rate_team(
    team: dict[str, Any], rules: dict[str, Any], season: str | None = None
) -> list[PlayerRatings]:
    return [rate_player(p, rules, season) for p in team["players"]]


def calibrate(
    rows: Iterable[dict[str, Any]], rules: dict[str, Any], season: str, min_samples: int = 10
) -> tuple[dict[str, Any], dict[str, int]]:
    """리그 모집단의 경기당 기록으로 각 구성요소의 mean/sd 를 다시 계산한다.

    rows 는 기록 필드(gp, ppg, ...)와 선택적으로 height_cm/weight_kg 를 가진 dict.
    min_games 이상 출전한 행만 표본으로 쓰며, 표본이 min_samples 미만인 입력은
    기존 값을 유지한다. (새 규칙, 입력별 표본 수)를 반환한다.
    """
    samples: dict[str, list[float]] = {}
    for row in rows:
        if (row.get("gp") or 0) < rules["min_games"]:
            continue
        for k in (*STAT_INPUTS, *BODY_INPUTS):
            v = row.get(k)
            if v is not None:
                samples.setdefault(k, []).append(float(v))

    new = copy.deepcopy(rules)
    counts = {k: len(v) for k, v in samples.items()}
    for rule in new["attributes"].values():
        for comp in rule.get("components", []):
            xs = samples.get(comp["input"], [])
            if len(xs) >= min_samples:
                sd = statistics.pstdev(xs)
                if sd > 0:
                    comp["mean"] = round(statistics.fmean(xs), 4)
                    comp["sd"] = round(sd, 4)
    # provisional 은 그대로 둔다: mean/sd 는 실측이 되지만 base/spread/league_offset 은
    # 게임 내 밸런스 확인 전까지 잠정값이다.
    new["stats_season"] = season
    return new, counts
