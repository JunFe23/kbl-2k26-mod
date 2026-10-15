"""kbl2k 명령줄 도구."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

from . import __version__
from .backup import BackupError, create_backup, restore_backup, verify_backup
from .dataset import RULES_FILE, DataError, load_dataset
from .fetch import fetch_league, fetch_players, league_file
from .game import (
    GameError,
    asset_summary,
    diff_snapshots,
    find_game,
    read_asset_manifest,
    save_snapshot,
    take_snapshot,
)
from .issues import has_errors
from .kbl_api import KblApiError, fetch_team_names, season_code
from .mapping import coverage
from .positions import export_csv, import_csv
from .ratings import KBL, calibrate, rate_team
from .validate import validate_dataset
from .venuelab import (
    ApplyReport,
    VenueLabError,
    apply_plan,
    build_plan,
    make_probe_runner,
    write_report,
)

DEFAULT_DATA = Path("data")


def cmd_validate(args: argparse.Namespace) -> int:
    issues = validate_dataset(args.data)
    shown = [i for i in issues if args.warnings or i.level == "error"]
    for i in shown:
        print(i)
    n_err = sum(i.level == "error" for i in issues)
    n_warn = len(issues) - n_err
    print(f"검증 완료: 오류 {n_err}건, 경고 {n_warn}건")
    return 1 if has_errors(issues) else 0


def _load_valid(data: Path):
    issues = validate_dataset(data)
    if has_errors(issues):
        for i in issues:
            if i.level == "error":
                print(i, file=sys.stderr)
        raise SystemExit(1)
    ds, _ = load_dataset(data)
    return ds


def _find_team(ds, key: str) -> dict:
    for file, team in ds.teams.items():
        if key in (team["id"], file, Path(file).stem):
            return team
    raise SystemExit(f"팀을 찾을 수 없습니다: {key} (가능: {[t['id'] for t in ds.teams.values()]})")


def cmd_ratings(args: argparse.Namespace) -> int:
    ds = _load_valid(args.data)
    team = _find_team(ds, args.team)
    rows = rate_team(team, ds.rules, args.season)
    if args.json:
        print(json.dumps([r.as_dict() for r in rows], ensure_ascii=False, indent=2))
        return 0
    if ds.rules.get("provisional"):
        print("※ 잠정 규칙(provisional) — 결과는 참고용입니다.\n")
    print(f"{team['name_ko']} ({team['season']})")
    print(f"{'선수':<10} {'POS':<6} {'기록 기준':<14} {'OVR':>4}  주요 능력치")
    for r in sorted(rows, key=lambda r: -r.ovr):
        top = sorted(r.attributes.items(), key=lambda kv: -kv[1].value)[:3]
        top_s = ", ".join(f"{k} {v.value}" for k, v in top)
        pos = "/".join(r.positions) or "-"
        print(f"{r.name_ko:<10} {pos:<6} {r.basis:<14} {r.ovr:>4}  {top_s}")
    return 0


def cmd_calibrate(args: argparse.Namespace) -> int:
    ds = _load_valid(args.data)
    league = ds.league.get(league_file(args.season))
    if league is not None:
        rows = league["players"]
        print(f"모집단: {league_file(args.season)} ({len(rows)}명)", file=sys.stderr)
    else:
        rows = [
            {**ln, "height_cm": p["height_cm"], "weight_kg": p["weight_kg"]}
            for t in ds.teams.values()
            for p in t["players"]
            for ln in p.get("stats") or []
            if ln["season"] == args.season and ln["league"] == KBL
        ]
        print(
            f"모집단: 로스터 선수 {len(rows)}명 (리그 파일 없음 — kbl2k fetch league 권장)",
            file=sys.stderr,
        )
    new, counts = calibrate(rows, ds.rules, args.season, args.min_samples)
    print(f"표본 수: {dict(sorted(counts.items()))}", file=sys.stderr)
    text = json.dumps(new, ensure_ascii=False, indent=2) + "\n"
    if args.write:
        (args.data / RULES_FILE).write_text(text, "utf-8", newline="\n")
        print(f"갱신: {args.data / RULES_FILE}", file=sys.stderr)
    else:
        print(text)
    return 0


def cmd_fetch_league(args: argparse.Namespace) -> int:
    try:
        path, n = fetch_league(args.data, args.season)
    except (KblApiError, ValueError) as e:
        print(f"수집 실패: {e}", file=sys.stderr)
        return 1
    print(f"저장: {path} ({n}명)")
    return cmd_validate(argparse.Namespace(data=args.data, warnings=False))


def cmd_fetch_players(args: argparse.Namespace) -> int:
    _load_valid(args.data)
    try:
        for s in args.seasons:
            season_code(s)
        names = fetch_team_names()
        result = fetch_players(args.data, set(args.seasons), team_names=names, delay=args.delay)
    except (KblApiError, ValueError) as e:
        print(f"수집 실패: {e}", file=sys.stderr)
        return 1
    none = [pid for pid, n in result.items() if n == 0]
    print(f"완료: {len(result)}명, 대상 시즌 KBL 기록 없음 {len(none)}명")
    return cmd_validate(argparse.Namespace(data=args.data, warnings=False))


def cmd_mapping(args: argparse.Namespace) -> int:
    ds = _load_valid(args.data)
    rows = coverage(ds.mapping, list(ds.teams.values()))
    if args.verbose:
        for r in rows:
            print(f"{r.entity_type:<7} {r.name:<12} {r.asset_type:<13} {r.status}")
    summary = Counter((r.asset_type, r.status) for r in rows)
    print("에셋 진행 현황:")
    for asset in sorted({a for a, _ in summary}):
        parts = ", ".join(f"{s} {n}" for (a, s), n in sorted(summary.items()) if a == asset)
        print(f"  {asset:<13} {parts}")
    return 0


def cmd_positions_export(args: argparse.Namespace) -> int:
    ds = _load_valid(args.data)
    text = export_csv(list(ds.teams.values()))
    if args.output:
        # utf-8-sig: 엑셀에서 한글이 깨지지 않도록 BOM 포함
        args.output.write_text(text, "utf-8-sig")
        print(f"내보냄: {args.output} — primary/secondary 열을 채운 뒤 import 하세요")
    else:
        sys.stdout.write(text)
    return 0


def cmd_positions_import(args: argparse.Namespace) -> int:
    changes, issues = import_csv(args.data, args.csv, apply=not args.dry_run)
    for i in issues:
        print(i)
    if has_errors(issues):
        print("가져오기 취소: 오류가 있어 아무것도 바꾸지 않았습니다")
        return 1
    for c in changes:
        old = "/".join(c.old) or "(미정)"
        new = "/".join(c.new) or "(미정)"
        print(f"{c.name_ko:<10} {old:>7} → {new}")
    verb = "변경 예정" if args.dry_run else "변경"
    print(f"{verb} {len(changes)}명")
    if not args.dry_run and changes:
        return cmd_validate(argparse.Namespace(data=args.data, warnings=True))
    return 0


def _game(args: argparse.Namespace):
    return find_game(args.steam_dir)


def cmd_game_info(args: argparse.Namespace) -> int:
    try:
        info = _game(args)
        summary = asset_summary(read_asset_manifest(info.install_dir))
    except GameError as e:
        print(f"확인 실패: {e}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps({**info.as_dict(), "assets": summary}, ensure_ascii=False, indent=2))
        return 0
    print(f"{info.name} (appid {info.appid})")
    print(f"  설치 폴더   {info.install_dir}")
    print(f"  Steam 빌드  {info.buildid} (업데이트 {info.last_updated})")
    print("  에셋 (manifest 기준):")
    for kind, s in summary.items():
        print(f"    {kind:<18} {s['count']:>5}개  ID {s['min']}~{s['max']}")
    return 0


def cmd_game_snapshot(args: argparse.Namespace) -> int:
    try:
        info = _game(args)
        target = args.dir or info.install_dir
        print(f"스냅샷 작성 중: {target}", file=sys.stderr)
        snap = take_snapshot(target, info.buildid)
        path = save_snapshot(snap, args.out, args.label)
    except GameError as e:
        print(f"스냅샷 실패: {e}", file=sys.stderr)
        return 1
    print(f"저장: {path} (파일 {len(snap['files'])}개, 빌드 {info.buildid})")
    return 0


def cmd_game_diff(args: argparse.Namespace) -> int:
    old = json.loads(args.old.read_text("utf-8"))
    if args.new:
        new = json.loads(args.new.read_text("utf-8"))
    else:
        try:
            info = _game(args)
        except GameError as e:
            print(f"확인 실패: {e}", file=sys.stderr)
            return 1
        new = take_snapshot(Path(old["game_dir"]), info.buildid, old.get("hash_limit", 64 << 20))
    d = diff_snapshots(old, new)
    if d.build_changed:
        print(f"빌드 변경: {old.get('buildid')} → {new.get('buildid')} (게임 업데이트)")
    for label, items in (("추가", d.added), ("삭제", d.removed), ("변경", d.changed)):
        for rel in items:
            print(f"{label}  {rel}")
    print(
        "변경 없음"
        if d.clean
        else f"추가 {len(d.added)} / 삭제 {len(d.removed)} / 변경 {len(d.changed)}"
    )
    return 0 if d.clean else 2


def cmd_venuelab_plan(args: argparse.Namespace) -> int:
    ds = _load_valid(args.data)
    plan = build_plan(list(ds.teams.values()), ds.rules)
    if not plan["teams"]:
        print("game_roster 와 nba_slot 이 지정된 팀이 없습니다", file=sys.stderr)
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(plan, ensure_ascii=False, indent=2) + "\n", "utf-8", newline="\n"
    )
    for team in plan["teams"]:
        print(f"{team['name_ko']} → {team['nba_slot']} ({len(team['players'])}명)")
        for p in team["players"]:
            mark = f"  ⚠ {p['name_review_reason']}" if p["name_needs_review"] else ""
            name = f"{p['first_name']} {p['last_name']}".strip()
            print(f"  #{p['jersey']:<3} {p['name_ko']:<8} {name:<24} OVR {p['ovr']}{mark}")
    print(f"저장: {args.output}")
    return 0


def parse_aliases(items: list[str]) -> dict[str, list[str]]:
    """'Chicago Bulls=Denver Bulls' → {'Chicago Bulls': ['Denver Bulls']}"""
    out: dict[str, list[str]] = {}
    for item in items:
        if "=" not in item:
            raise SystemExit(f"--alias 형식: '원래 팀=게임에 보이는 이름' (받은 값: {item!r})")
        k, v = (x.strip() for x in item.split("=", 1))
        out.setdefault(k, []).append(v)
    return out


def cmd_venuelab_apply(args: argparse.Namespace) -> int:
    plan = json.loads(args.plan.read_text("utf-8"))
    report_path = args.report or Path("game_backup/venuelab") / (
        f"apply-{'write' if args.apply else 'dryrun'}-"
        + datetime.now().strftime("%Y%m%d-%H%M%S")
        + ".jsonl"
    )
    report = ApplyReport()
    catalog_path = report_path.with_name(report_path.stem + "-catalog.json")
    failed = None
    try:
        probe = make_probe_runner(args.venuelab_dir)
        apply_plan(
            plan,
            probe,
            write=args.apply,
            report=report,
            progress=lambda m: print(m, file=sys.stderr, flush=True),
            catalog_path=catalog_path,
            aliases=parse_aliases(args.alias or []),
        )
    except VenueLabError as e:
        failed = str(e)
        report.log(stage="abort", status="error", reason=failed)
    except KeyboardInterrupt:
        failed = "사용자가 중단함"
        report.log(stage="abort", status="error", reason=failed)
    write_report(report, report_path)
    contexts = {
        e.get("context") for e in report.events if e.get("stage") == "plan" and e.get("context")
    }
    if contexts:
        print(f"불러와진 로스터(VenueLab 판단): {', '.join(sorted(contexts))}")
    for status in ("planned", "dry_run", "write_readback_ok", "unchanged", "rejected", "error"):
        n = report.count(status)
        if n:
            print(f"{status:<18} {n}")
    print(f"보고서: {report_path}")
    if failed:
        print(f"중단: {failed}", file=sys.stderr)
        return 1
    bad = report.count("error") + report.count("rejected")
    if not args.apply:
        print("dry-run: 아무것도 쓰지 않았습니다. 실제로 쓰려면 --apply")
    return 1 if bad else 0


def cmd_assets_logo(args: argparse.Namespace) -> int:
    from .assets import AssetError, make_logo

    try:
        r = make_logo(args.src, args.dst, args.size, args.margin, args.gap_radius)
    except AssetError as e:
        print(f"변환 실패: {e}", file=sys.stderr)
        return 1
    print(f"{r['method']}: {r['src']} → {r['dst']} {r['size'][0]}x{r['size'][1]}")
    return 0


def cmd_venuelab_capture_team(args: argparse.Namespace) -> int:
    from .venuelab import capture_team

    names = [args.team] + (args.alt or [])
    try:
        cap = capture_team(make_probe_runner(args.venuelab_dir), names, args.label)
    except VenueLabError as e:
        print(f"캡처 실패: {e}", file=sys.stderr)
        return 1
    out = Path("game_backup/venuelab/team-captures") / f"{args.label}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(cap, ensure_ascii=False, indent=1), "utf-8", newline="\n")
    t = cap["team"]
    print(
        f"캡처: {t.get('city')} {t.get('nickname')} ({t.get('abbr')}) {cap['team_pointer']} → {out}"
    )
    return 0


def cmd_venuelab_diff_team(args: argparse.Namespace) -> int:
    from .venuelab import diff_team_captures

    a = json.loads(args.a.read_text("utf-8"))
    b = json.loads(args.b.read_text("utf-8"))
    diffs = diff_team_captures(a["raw_hex"], b["raw_hex"])
    print(f"{a['label']} → {b['label']}: 변경 구간 {len(diffs)}개")
    for d in diffs:
        text = (
            f"  [{d['before_text']!r} → {d['after_text']!r}]"
            if d["before_text"] or d["after_text"]
            else ""
        )
        print(
            f"{d['offset']:>8} ({d['length']:>3}B) {d['before'][:47]:<47} → {d['after'][:47]}{text}"
        )
    return 0


def cmd_backup(args: argparse.Namespace) -> int:
    try:
        dest = create_backup(args.game_dir, args.files, args.out, args.label)
    except BackupError as e:
        print(f"백업 실패: {e}", file=sys.stderr)
        return 1
    print(f"백업 완료: {dest}")
    return 0


def cmd_verify_backup(args: argparse.Namespace) -> int:
    try:
        problems = verify_backup(args.backup_dir)
    except BackupError as e:
        print(f"검증 실패: {e}", file=sys.stderr)
        return 1
    for p in problems:
        print(p)
    print("백업 정상" if not problems else f"문제 {len(problems)}건")
    return 1 if problems else 0


def cmd_restore(args: argparse.Namespace) -> int:
    try:
        steps = restore_backup(args.backup_dir, args.game_dir, apply=args.apply, force=args.force)
    except BackupError as e:
        print(f"복구 실패: {e}", file=sys.stderr)
        return 1
    for s in steps:
        print(f"{s.action:<9} {s.path}")
    print("복구 완료" if args.apply else "dry-run (실제로 쓰려면 --apply)")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="kbl2k", description="NBA 2K26 KBL 모드 데이터 도구")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    p.add_argument("--data", type=Path, default=DEFAULT_DATA, help="데이터 디렉터리 (기본: data)")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("validate", help="스키마 + 의미 검증")
    s.add_argument("-w", "--warnings", action="store_true", help="경고도 출력")
    s.set_defaults(func=cmd_validate)

    s = sub.add_parser("ratings", help="팀 선수 능력치 산정")
    s.add_argument("team", help="팀 id 또는 파일명 (예: seoul-sk)")
    s.add_argument("--season", help="기록 시즌 (기본: 규칙의 stats_season → 최신)")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_ratings)

    s = sub.add_parser("calibrate", help="데이터로 평균/표준편차 재계산")
    s.add_argument("season")
    s.add_argument("--min-samples", type=int, default=10)
    s.add_argument("--write", action="store_true", help="rating_rules.json 덮어쓰기")
    s.set_defaults(func=cmd_calibrate)

    s = sub.add_parser("fetch", help="KBL 공식 기록 내려받기")
    f_sub = s.add_subparsers(dest="fetch_command", required=True)
    f = f_sub.add_parser("league", help="시즌 전체 선수 기록 → data/league/ (보정 모집단)")
    f.add_argument("season", help="예: 2025-26")
    f.set_defaults(func=cmd_fetch_league)
    f = f_sub.add_parser("players", help="로스터 선수별 KBL 시즌 이력 → 팀 파일 stats")
    f.add_argument("seasons", nargs="+", help="반영할 시즌 (예: 2025-26 2024-25)")
    f.add_argument("--delay", type=float, default=1.0, help="요청 간 대기(초)")
    f.set_defaults(func=cmd_fetch_players)

    s = sub.add_parser("mapping", help="에셋 매핑 진행 현황")
    s.add_argument("-v", "--verbose", action="store_true")
    s.set_defaults(func=cmd_mapping)

    s = sub.add_parser("positions", help="2K26 포지션 직접 입력 (CSV)")
    pos_sub = s.add_subparsers(dest="pos_command", required=True)
    e = pos_sub.add_parser("export", help="포지션 입력용 CSV 내보내기")
    e.add_argument("-o", "--output", type=Path, help="파일 경로 (생략 시 화면 출력)")
    e.set_defaults(func=cmd_positions_export)
    m = pos_sub.add_parser("import", help="CSV 의 primary/secondary 를 팀 파일에 반영")
    m.add_argument("csv", type=Path)
    m.add_argument("--dry-run", action="store_true", help="변경 내용만 보여주기")
    m.set_defaults(func=cmd_positions_import)

    s = sub.add_parser("game", help="설치된 NBA 2K26 확인·변경 감시 (읽기 전용)")
    s.add_argument("--steam-dir", type=Path, help="Steam 폴더 (기본: 레지스트리)")
    g_sub = s.add_subparsers(dest="game_command", required=True)
    g = g_sub.add_parser("info", help="설치 경로, Steam 빌드, 에셋 요약")
    g.add_argument("--json", action="store_true")
    g.set_defaults(func=cmd_game_info)
    g = g_sub.add_parser("snapshot", help="게임 폴더 파일 목록·해시 기록")
    g.add_argument("--out", type=Path, default=Path("game_backup/snapshots"))
    g.add_argument("--label", help="예: before-2kvenuelab")
    g.add_argument(
        "--dir", type=Path, help="게임 폴더 대신 기록할 폴더 (예: Steam userdata 세이브 폴더)"
    )
    g.set_defaults(func=cmd_game_snapshot)
    g = g_sub.add_parser(
        "diff", help="스냅샷 비교 (new 생략 시 현재 상태와 비교). 변경 있으면 exit 2"
    )
    g.add_argument("old", type=Path)
    g.add_argument("new", type=Path, nargs="?")
    g.set_defaults(func=cmd_game_diff)

    s = sub.add_parser("venuelab", help="2KVenueLab 으로 게임 로스터 일괄 입력 (ADR-0014/0015)")
    v_sub = s.add_subparsers(dest="venuelab_command", required=True)
    v = v_sub.add_parser("plan", help="게임 입력 계획 JSON 생성 (게임 불필요)")
    v.add_argument("-o", "--output", type=Path, default=Path("game_backup/venuelab/plan.json"))
    v.set_defaults(func=cmd_venuelab_plan)
    v = v_sub.add_parser("apply", help="오프라인 게임 실행 중 계획 적용 (기본 dry-run)")
    v.add_argument("--plan", type=Path, default=Path("game_backup/venuelab/plan.json"))
    v.add_argument("--venuelab-dir", type=Path, default=Path("D:/2K Tools/2KVenueLab-2.15"))
    v.add_argument("--apply", action="store_true", help="실제로 게임 메모리에 쓴다")
    v.add_argument("--report", type=Path, help="결과 JSONL 경로")
    v.add_argument(
        "--alias",
        action="append",
        help="팀 이름이 바뀐 경우 찾을 이름, 예: 'Chicago Bulls=Denver Bulls'",
    )
    v.set_defaults(func=cmd_venuelab_apply)
    v = v_sub.add_parser("capture-team", help="팀 레코드 바이트 캡처 (읽기 전용, 분석용)")
    v.add_argument("team", help="게임에 보이는 팀 이름, 예: 'Chicago Bulls'")
    v.add_argument("--alt", action="append", help="다른 이름으로도 찾기")
    v.add_argument("--label", required=True)
    v.add_argument("--venuelab-dir", type=Path, default=Path("D:/2K Tools/2KVenueLab-2.15"))
    v.set_defaults(func=cmd_venuelab_capture_team)
    v = v_sub.add_parser("diff-team", help="두 팀 레코드 캡처 비교")
    v.add_argument("a", type=Path)
    v.add_argument("b", type=Path)
    v.set_defaults(func=cmd_venuelab_diff_team)

    s = sub.add_parser("assets", help="비주얼 에셋 준비 (ADR-0019)")
    a_sub = s.add_subparsers(dest="assets_command", required=True)
    a = a_sub.add_parser("logo", help="로고(JPG/PNG/SVG) → 투명 정사각 PNG")
    a.add_argument("src", type=Path)
    a.add_argument("dst", type=Path)
    a.add_argument("--size", type=int, default=1024)
    a.add_argument("--margin", type=float, default=0.06, help="가장자리 여백 비율")
    a.add_argument("--gap-radius", type=int, help="JPG 로고 틈 채우기 반경(px, 0=끔, 기본 자동)")
    a.set_defaults(func=cmd_assets_logo)

    s = sub.add_parser("backup", help="게임 파일 백업 (게임 폴더는 읽기만 함)")
    s.add_argument("--game-dir", type=Path, required=True)
    s.add_argument("--out", type=Path, default=Path("game_backup"))
    s.add_argument("--label")
    s.add_argument("files", nargs="+", help="게임 폴더 기준 상대 경로")
    s.set_defaults(func=cmd_backup)

    s = sub.add_parser("verify-backup", help="백업본 해시 검증")
    s.add_argument("backup_dir", type=Path)
    s.set_defaults(func=cmd_verify_backup)

    s = sub.add_parser("restore", help="백업 복구 (기본 dry-run)")
    s.add_argument("backup_dir", type=Path)
    s.add_argument("--game-dir", type=Path, required=True)
    s.add_argument("--apply", action="store_true")
    s.add_argument("--force", action="store_true", help="manifest 의 게임 폴더와 달라도 진행")
    s.set_defaults(func=cmd_restore)
    return p


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except DataError as e:
        print(e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
