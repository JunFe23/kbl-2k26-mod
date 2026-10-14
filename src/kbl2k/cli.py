"""kbl2k 명령줄 도구."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from . import __version__
from .backup import BackupError, create_backup, restore_backup, verify_backup
from .dataset import RULES_FILE, DataError, load_dataset
from .issues import has_errors
from .mapping import coverage
from .ratings import calibrate, rate_team
from .validate import validate_dataset

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
    print(f"{'선수':<10} {'POS':<6} {'시즌':<8} {'OVR':>4}  주요 능력치")
    for r in sorted(rows, key=lambda r: -r.ovr):
        top = sorted(r.attributes.items(), key=lambda kv: -kv[1].value)[:3]
        top_s = ", ".join(f"{k} {v.value}" for k, v in top)
        pos = "/".join(r.positions) or "-"
        print(f"{r.name_ko:<10} {pos:<6} {r.season or '-':<8} {r.ovr:>4}  {top_s}")
    return 0


def cmd_calibrate(args: argparse.Namespace) -> int:
    ds = _load_valid(args.data)
    players = [p for t in ds.teams.values() for p in t["players"]]
    new, counts = calibrate(players, ds.rules, args.season, args.min_samples)
    print(f"표본 수: {dict(sorted(counts.items()))}", file=sys.stderr)
    text = json.dumps(new, ensure_ascii=False, indent=2) + "\n"
    if args.write:
        (args.data / RULES_FILE).write_text(text, "utf-8")
        print(f"갱신: {args.data / RULES_FILE}", file=sys.stderr)
    else:
        print(text)
    return 0


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

    s = sub.add_parser("mapping", help="에셋 매핑 진행 현황")
    s.add_argument("-v", "--verbose", action="store_true")
    s.set_defaults(func=cmd_mapping)

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
