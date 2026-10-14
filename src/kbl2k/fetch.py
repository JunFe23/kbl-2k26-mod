"""KBL 기록을 내려받아 data/ 에 반영한다.

- league: 시즌 전체 선수 기록 → data/league/kbl-<season>.json (능력치 보정 모집단)
- players: 로스터 선수별 KBL 1군 정규시즌 이력 → 팀 파일의 stats (KBL 행만 교체, 해외 기록은 유지)
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

from . import kbl_api
from .dataset import LEAGUE_DIR, SOURCES_FILE, TEAMS_DIR, read_json
from .ratings import KBL

HISTORY_SOURCE = "kbl-player-season-history"


def league_file(season: str) -> str:
    return f"{LEAGUE_DIR}/kbl-{season}.json"


def league_source_id(season: str) -> str:
    return f"kbl-stats-{season}"


def write_json(path: Path, doc: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", "utf-8", newline="\n")


def ensure_source(data_root: Path, source: dict[str, Any]) -> None:
    """sources.json 에 같은 id 가 있으면 retrieved_at 만 갱신, 없으면 추가."""
    path = data_root / SOURCES_FILE
    doc = read_json(path)
    for s in doc["sources"]:
        if s["id"] == source["id"]:
            s["retrieved_at"] = source["retrieved_at"]
            break
    else:
        doc["sources"].append(source)
    write_json(path, doc)


def build_league_doc(season: str, raw_rows: list[dict[str, Any]], today: str) -> dict[str, Any]:
    players = [
        {
            "kbl_player_id": str(r["playerNo"]),
            "name_ko": r.get("kname") or "",
            "name_en": r.get("ename"),
            "team_code": str(r.get("teamCode") or ""),
            **kbl_api.league_row_to_stats(r),
        }
        for r in raw_rows
    ]
    players.sort(key=lambda p: (p["team_code"], p["kbl_player_id"]))
    return {
        "league": KBL,
        "season": season,
        "competition": "regular_season",
        "kbl_season_code": kbl_api.season_code(season),
        "source_id": league_source_id(season),
        "retrieved_at": today,
        "players": players,
    }


def fetch_league(
    data_root: Path,
    season: str,
    fetch: Callable[[str], list[dict[str, Any]]] = kbl_api.fetch_league_rows,
    today: str | None = None,
) -> tuple[Path, int]:
    today = today or date.today().isoformat()
    doc = build_league_doc(season, fetch(season), today)
    path = data_root / league_file(season)
    write_json(path, doc)
    ensure_source(data_root, {
        "id": league_source_id(season),
        "title": f"KBL {season} 정규리그 전체 선수 기록 (traditional)",
        "url": f"{kbl_api.STATS_API}/api/records/player/general/traditional"
               f"?seasonCode={kbl_api.season_code(season)}&gameCode=01",
        "publisher": "KBL",
        "official": True,
        "retrieved_at": today,
        "notes": "kbl.or.kr 기록 페이지가 사용하는 API. Origin/Referer https://www.kbl.or.kr 필요",
    })  # fmt: skip
    return path, len(doc["players"])


def merge_kbl_lines(
    existing: list[dict[str, Any]], fresh: list[dict[str, Any]], seasons: set[str]
) -> list[dict[str, Any]]:
    """대상 시즌의 KBL 행만 새 값으로 교체. 해외/다른 시즌 행은 그대로."""
    kept = [ln for ln in existing if not (ln["league"] == KBL and ln["season"] in seasons)]
    merged = kept + fresh
    return sorted(merged, key=lambda ln: (ln["season"], ln["league"] == KBL), reverse=True)


def fetch_players(
    data_root: Path,
    seasons: set[str],
    fetch: Callable[[str], dict[str, Any]] = kbl_api.fetch_player_history,
    team_names: dict[str, str] | None = None,
    delay: float = 1.0,
    today: str | None = None,
    log: Callable[[str], None] = print,
) -> dict[str, int]:
    """로스터 선수별 KBL 이력을 받아 stats 에 반영. {player_id: 반영된 행 수}."""
    today = today or date.today().isoformat()
    result: dict[str, int] = {}
    first = True
    for path in sorted((data_root / TEAMS_DIR).glob("*.json")):
        team = read_json(path)
        for p in team["players"]:
            pid = p.get("kbl_player_id")
            if not pid:
                continue
            if not first:
                time.sleep(delay)
            first = False
            fresh = kbl_api.history_to_stat_lines(fetch(pid), HISTORY_SOURCE, team_names, seasons)
            merged = merge_kbl_lines(p.get("stats") or [], fresh, seasons)
            if merged:
                p["stats"] = merged
            else:
                p.pop("stats", None)
            result[p["id"]] = len(fresh)
            log(f"{p['name_ko']}: KBL {len(fresh)}개 시즌")
        write_json(path, team)

    ensure_source(data_root, {
        "id": HISTORY_SOURCE,
        "title": "KBL 선수별 1군 정규시즌 기록 이력",
        "url": f"{kbl_api.S2I_API}/players/categories/season/",
        "publisher": "KBL",
        "official": True,
        "retrieved_at": today,
        "notes": "kbl.or.kr 선수 상세 페이지가 사용하는 API. URL 끝에 kbl_player_id. "
                 "Origin/Referer https://www.kbl.or.kr 필요",
    })  # fmt: skip
    return result
