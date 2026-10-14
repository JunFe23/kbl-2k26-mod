"""게임 파일 백업/복구.

원칙
- 백업은 게임 폴더를 읽기만 한다.
- 백업 폴더는 게임 폴더 밖에 있어야 한다.
- manifest.json 에 상대 경로·크기·SHA-256 을 기록하고, 복구 전 백업본 해시를 검증한다.
- restore 는 기본이 dry-run 이며 apply=True 일 때만 게임 폴더에 쓴다.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Literal

MANIFEST = "manifest.json"
FILES_DIR = "files"
CHUNK = 1024 * 1024


class BackupError(Exception):
    pass


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(CHUNK):
            h.update(chunk)
    return h.hexdigest()


def _safe_rel(game_dir: Path, rel: str) -> PurePosixPath:
    p = PurePosixPath(rel.replace("\\", "/"))
    if p.is_absolute() or ".." in p.parts or not p.parts or Path(rel).drive:
        raise BackupError(f"게임 폴더 기준 상대 경로만 허용: {rel!r}")
    if not (game_dir / p).resolve().is_relative_to(game_dir.resolve()):
        raise BackupError(f"게임 폴더 밖 경로: {rel!r}")
    return p


def create_backup(
    game_dir: Path, rel_files: list[str], backup_root: Path, label: str | None = None
) -> Path:
    game_dir, backup_root = Path(game_dir), Path(backup_root)
    if not game_dir.is_dir():
        raise BackupError(f"게임 폴더가 없습니다: {game_dir}")
    if backup_root.resolve().is_relative_to(game_dir.resolve()):
        raise BackupError("백업 폴더는 게임 폴더 밖에 있어야 합니다")
    if not rel_files:
        raise BackupError("백업할 파일을 지정하세요")

    rels = [_safe_rel(game_dir, r) for r in rel_files]
    for r in rels:
        if not (game_dir / r).is_file():
            raise BackupError(f"파일이 없습니다: {r}")

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    name = f"{stamp}-{label}" if label else stamp
    dest = backup_root / name
    n = 1
    while dest.exists():
        n += 1
        dest = backup_root / f"{name}-{n}"
    (dest / FILES_DIR).mkdir(parents=True)

    entries = []
    for r in rels:
        src = game_dir / r
        out = dest / FILES_DIR / r
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, out)
        digest = sha256_file(src)
        if sha256_file(out) != digest:
            raise BackupError(f"복사본 해시 불일치: {r}")
        entries.append({"path": r.as_posix(), "size": src.stat().st_size, "sha256": digest})

    manifest = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "game_dir": str(game_dir.resolve()),
        "files": entries,
    }
    (dest / MANIFEST).write_text(json.dumps(manifest, ensure_ascii=False, indent=2), "utf-8")
    return dest


def read_manifest(backup_dir: Path) -> dict:
    path = Path(backup_dir) / MANIFEST
    if not path.is_file():
        raise BackupError(f"manifest 없음: {path}")
    return json.loads(path.read_text("utf-8"))


def verify_backup(backup_dir: Path) -> list[str]:
    """백업본 무결성 검사. 문제 목록(비어 있으면 정상)."""
    backup_dir = Path(backup_dir)
    problems = []
    for e in read_manifest(backup_dir)["files"]:
        f = backup_dir / FILES_DIR / e["path"]
        if not f.is_file():
            problems.append(f"누락: {e['path']}")
        elif sha256_file(f) != e["sha256"]:
            problems.append(f"해시 불일치: {e['path']}")
    return problems


Action = Literal["restore", "create", "unchanged"]


@dataclass(frozen=True)
class RestoreStep:
    path: str
    action: Action


def restore_backup(
    backup_dir: Path, game_dir: Path, apply: bool = False, force: bool = False
) -> list[RestoreStep]:
    backup_dir, game_dir = Path(backup_dir), Path(game_dir)
    manifest = read_manifest(backup_dir)
    if not force and Path(manifest["game_dir"]) != game_dir.resolve():
        raise BackupError(
            f"백업 대상 폴더({manifest['game_dir']})와 다릅니다. 의도한 것이면 force 사용"
        )
    problems = verify_backup(backup_dir)
    if problems:
        raise BackupError("백업본 손상: " + "; ".join(problems))

    steps: list[RestoreStep] = []
    for e in manifest["files"]:
        rel = _safe_rel(game_dir, e["path"])
        target = game_dir / rel
        if not target.exists():
            action: Action = "create"
        elif sha256_file(target) == e["sha256"]:
            action = "unchanged"
        else:
            action = "restore"
        steps.append(RestoreStep(e["path"], action))

    if apply:
        for step, e in zip(steps, manifest["files"], strict=True):
            if step.action == "unchanged":
                continue
            target = game_dir / step.path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup_dir / FILES_DIR / step.path, target)
            if sha256_file(target) != e["sha256"]:
                raise BackupError(f"복구 후 해시 불일치: {step.path}")
    return steps
