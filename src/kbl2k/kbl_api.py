"""KBL 공식 사이트(kbl.or.kr) 가 사용하는 기록 API 클라이언트.

공개 문서가 없는 사이트 내부 API 이므로 응답 형식이 바뀔 수 있다.
요청 수를 최소화하고(페이지당 200명, 요청 간 지연), 원본 응답은 변환 함수로만 다룬다.

시즌 코드 (1군): 홀수, 2*시작연도 - 4003  → 2025-26 = 47, 2026-27 = 49
  - 검증: 47 은 API 에서 '정규시즌', 48 은 'D리그'
  - 35 = 2019-20 (코로나 조기 종료로 43경기) 와 일치
"""

from __future__ import annotations

import json
import time
import urllib.request
from typing import Any

from .ratings import KBL

STATS_API = "https://api-stats.kbl.or.kr"
S2I_API = "https://kbl-api.sports2i.com/api/v1"
KBL_API = "https://api.kbl.or.kr"
REGULAR_SEASON = "01"
PAGE_SIZE = 200  # API 가 tinyint 로 받으므로 255 이하
HEADERS = {
    "Origin": "https://www.kbl.or.kr",
    "Referer": "https://www.kbl.or.kr/",
    "Accept": "application/json",
    "User-Agent": "kbl2k/0.1 (personal mod data pipeline)",
}


class KblApiError(Exception):
    pass


def season_code(season: str) -> int:
    start = int(season[:4])
    if not 2010 <= start <= 2100 or season[4:] != f"-{(start + 1) % 100:02d}":
        raise ValueError(f"시즌 형식 오류: {season!r} (예: 2025-26)")
    return 2 * start - 4003


def code_to_season(code: int | str) -> str:
    code = int(code)
    if code % 2 == 0:
        raise ValueError(f"1군 시즌 코드가 아님(짝수는 D리그): {code}")
    start = (code + 4003) // 2
    return f"{start}-{(start + 1) % 100:02d}"


def get_json(url: str, extra_headers: dict[str, str] | None = None, timeout: float = 30) -> Any:
    req = urllib.request.Request(url, headers={**HEADERS, **(extra_headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:  # noqa: BLE001 — 네트워크/파싱 오류를 한 종류로 보고
        raise KblApiError(f"요청 실패: {url}: {e}") from e


# --- 변환 (순수 함수, 테스트 대상) -------------------------------------------------


def _pg(total: float | None, gp: int) -> float | None:
    return None if total is None or not gp else round(total / gp, 2)


def _pct(made: float | None, att: float | None) -> float | None:
    return None if not att or made is None else round(made / att, 4)


def league_row_to_stats(row: dict[str, Any]) -> dict[str, Any]:
    """records/player/general/traditional 의 한 행(시즌 합계) → 경기당 기록.

    fdg/fdgA = 전체 야투, fg/fgA = 2점, threep/threepA = 3점.
    """
    gp = int(row["gameCount"])
    return {
        "gp": gp,
        "mpg": _pg((row.get("playSec") or 0) / 60, gp),
        "ppg": _pg(row.get("score"), gp),
        "rpg": _pg(row.get("rb"), gp),
        "orpg": _pg(row.get("oR"), gp),
        "drpg": _pg(row.get("dR"), gp),
        "apg": _pg(row.get("aS"), gp),
        "spg": _pg(row.get("sT"), gp),
        "bpg": _pg(row.get("bS"), gp),
        "tpg": _pg(row.get("tO"), gp),
        "fg_pct": _pct(row.get("fdg"), row.get("fdgA")),
        "fg3_pct": _pct(row.get("threep"), row.get("threepA")),
        "ft_pct": _pct(row.get("ft"), row.get("ftA")),
        "fg3a_pg": _pg(row.get("threepA"), gp),
        "fta_pg": _pg(row.get("ftA"), gp),
    }


def history_row_to_stats(row: dict[str, Any]) -> dict[str, Any]:
    """players/categories/season 의 RegularSeasonRecords 한 행 → 경기당 기록."""
    gp = int(row["gameCount"])
    return {
        "gp": gp,
        "mpg": _pg((row.get("sumPlaySec") or 0) / 60, gp),
        "ppg": _pg(row.get("sumScore"), gp),
        "rpg": _pg(row.get("sumRb"), gp),
        "orpg": _pg(row.get("sumOR"), gp),
        "drpg": _pg(row.get("sumDR"), gp),
        "apg": _pg(row.get("sumAS"), gp),
        "spg": _pg(row.get("sumSt"), gp),
        "bpg": _pg(row.get("sumBs"), gp),
        "tpg": _pg(row.get("sumTo"), gp),
        "fg_pct": _pct(row.get("sumFdg"), row.get("sumFdgA")),
        "fg3_pct": _pct(row.get("sumThreeP"), row.get("sumThreePA")),
        "ft_pct": _pct(row.get("sumFt"), row.get("sumFtA")),
        "fg3a_pg": _pg(row.get("sumThreePA"), gp),
        "fta_pg": _pg(row.get("sumFtA"), gp),
    }


def history_to_stat_lines(
    data: dict[str, Any],
    source_id: str,
    team_names: dict[str, str] | None = None,
    seasons: set[str] | None = None,
) -> list[dict[str, Any]]:
    """선수 시즌 이력 응답 → stat_line 목록 (1군 정규시즌만, 최신순)."""
    lines = []
    for row in data.get("RegularSeasonRecords") or []:
        code = int(row["seasonCode"])
        if code % 2 == 0:
            continue
        season = code_to_season(code)
        if seasons is not None and season not in seasons:
            continue
        team_code = str(row.get("teamCode") or "")
        lines.append({
            "season": season,
            "league": KBL,
            "team": (team_names or {}).get(team_code, f"KBL 팀코드 {team_code}"),
            "competition": "regular_season",
            "source_id": source_id,
            **history_row_to_stats(row),
        })  # fmt: skip
    return sorted(lines, key=lambda ln: ln["season"], reverse=True)


# --- 네트워크 ------------------------------------------------------------------


def fetch_league_rows(season: str, delay: float = 1.0) -> list[dict[str, Any]]:
    code = season_code(season)
    rows: list[dict[str, Any]] = []
    page = 1
    while True:
        url = (
            f"{STATS_API}/api/records/player/general/traditional?seasonCode={code}"
            f"&gameCode={REGULAR_SEASON}&sortDataSc=SCORE&sortOrderSc=DESC"
            f"&listCn={PAGE_SIZE}&pageNo={page}&ruleCk=0"
        )
        data = get_json(url).get("data") or []
        rows += data
        total = data[0].get("totalCn", 0) if data else 0
        if not data or len(rows) >= total:
            break
        page += 1
        time.sleep(delay)
    bad = {r.get("seasonCode") for r in rows} - {code}
    if bad:
        raise KblApiError(f"시즌 코드 불일치: 요청 {code}, 응답 {bad}")
    return rows


def fetch_player_history(kbl_player_id: str) -> dict[str, Any]:
    return get_json(f"{S2I_API}/players/categories/season/{kbl_player_id}")


def fetch_team_names() -> dict[str, str]:
    data = get_json(
        f"{KBL_API}/common/teamList",
        {"Channel": "WEB", "X-Requested-With": "XMLHttpRequest", "TeamCode": "XX"},
    )
    items = data.get("data") if isinstance(data, dict) else data
    return {str(t["teamCode"]): t["teamNameFull"] for t in items or []}
