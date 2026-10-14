"""설치된 NBA 2K26 정보 확인과 게임 폴더 변경 감시 (읽기 전용).

- info: Steam 레지스트리 → libraryfolders.vdf → appmanifest_<appid>.acf 에서 설치 경로·빌드 확인
- snapshot: 게임 폴더의 모든 파일 크기·수정시각(+작은 파일은 SHA-256) 기록. 게임 폴더 밖에 저장
- diff: 두 스냅샷 비교 → 외부 도구가 무엇을 추가/삭제/변경했는지 확인

게임 폴더에는 절대 쓰지 않는다.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

NBA2K26_APPID = "3472040"
HASH_LIMIT = 64 * 1024 * 1024  # 이보다 큰 파일(아카이브)은 크기·수정시각만 비교
_KV = re.compile(r'"([^"]+)"\s+"([^"]*)"')


class GameError(Exception):
    pass


def parse_vdf_pairs(text: str) -> list[tuple[str, str]]:
    """Valve KeyValues 텍스트의 "키" "값" 쌍(중첩 무시)."""
    return [(k, v.replace("\\\\", "\\")) for k, v in _KV.findall(text)]


def library_paths(steam_dir: Path) -> list[Path]:
    vdf = steam_dir / "steamapps" / "libraryfolders.vdf"
    paths = [steam_dir]
    if vdf.is_file():
        paths += [
            Path(v) for k, v in parse_vdf_pairs(vdf.read_text("utf-8", "replace")) if k == "path"
        ]
    seen: list[Path] = []
    for p in paths:
        if p.resolve() not in [s.resolve() for s in seen]:
            seen.append(p)
    return seen


def steam_dir_from_registry() -> Path | None:
    if sys.platform != "win32":
        return None
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as key:
            return Path(winreg.QueryValueEx(key, "SteamPath")[0])
    except OSError:
        return None


@dataclass(frozen=True)
class GameInfo:
    name: str
    appid: str
    install_dir: Path
    buildid: str
    last_updated: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "appid": self.appid,
            "install_dir": str(self.install_dir),
            "buildid": self.buildid,
            "last_updated": self.last_updated,
        }


def read_app_manifest(acf: Path, library: Path) -> GameInfo:
    kv = dict(parse_vdf_pairs(acf.read_text("utf-8", "replace")))
    updated = kv.get("LastUpdated")
    return GameInfo(
        name=kv.get("name", ""),
        appid=kv.get("appid", ""),
        install_dir=library / "steamapps" / "common" / kv.get("installdir", ""),
        buildid=kv.get("buildid", ""),
        last_updated=datetime.fromtimestamp(int(updated)).date().isoformat() if updated else None,
    )


def find_game(steam_dir: Path | None = None, appid: str = NBA2K26_APPID) -> GameInfo:
    steam_dir = steam_dir or steam_dir_from_registry()
    if steam_dir is None:
        raise GameError("Steam 설치 경로를 찾을 수 없습니다 (--steam-dir 로 지정)")
    for lib in library_paths(Path(steam_dir)):
        acf = lib / "steamapps" / f"appmanifest_{appid}.acf"
        if acf.is_file():
            info = read_app_manifest(acf, lib)
            if not info.install_dir.is_dir():
                raise GameError(f"설치 폴더가 없습니다: {info.install_dir}")
            return info
    raise GameError(f"appid {appid} 가 설치된 Steam 라이브러리가 없습니다")


# --- 스냅샷 -------------------------------------------------------------------


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def take_snapshot(
    game_dir: Path, buildid: str | None = None, hash_limit: int = HASH_LIMIT
) -> dict[str, Any]:
    game_dir = Path(game_dir)
    files: dict[str, dict[str, Any]] = {}
    for p in sorted(game_dir.rglob("*")):
        if not p.is_file():
            continue
        st = p.stat()
        entry: dict[str, Any] = {"size": st.st_size, "mtime_ns": st.st_mtime_ns}
        if st.st_size <= hash_limit:
            entry["sha256"] = _sha256(p)
        files[p.relative_to(game_dir).as_posix()] = entry
    return {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "game_dir": str(game_dir.resolve()),
        "buildid": buildid,
        "hash_limit": hash_limit,
        "files": files,
    }


def save_snapshot(snap: dict[str, Any], out_dir: Path, label: str | None = None) -> Path:
    out_dir = Path(out_dir)
    if out_dir.resolve().is_relative_to(Path(snap["game_dir"])):
        raise GameError("스냅샷은 게임 폴더 밖에 저장해야 합니다")
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = out_dir / (f"{stamp}-{label}.json" if label else f"{stamp}.json")
    n = 1
    while path.exists():
        n += 1
        path = path.with_name(f"{path.stem}-{n}.json")
    path.write_text(json.dumps(snap, ensure_ascii=False, indent=1), "utf-8")
    return path


@dataclass(frozen=True)
class SnapshotDiff:
    added: list[str]
    removed: list[str]
    changed: list[str]
    build_changed: bool

    @property
    def clean(self) -> bool:
        return not (self.added or self.removed or self.changed or self.build_changed)


def diff_snapshots(old: dict[str, Any], new: dict[str, Any]) -> SnapshotDiff:
    a, b = old["files"], new["files"]
    changed = []
    for rel in sorted(a.keys() & b.keys()):
        x, y = a[rel], b[rel]
        if x["size"] != y["size"] or x.get("sha256") != y.get("sha256"):
            changed.append(rel)
        elif "sha256" not in x and x["mtime_ns"] != y["mtime_ns"]:
            changed.append(rel)  # 큰 파일은 수정시각으로 판단
    return SnapshotDiff(
        added=sorted(b.keys() - a.keys()),
        removed=sorted(a.keys() - b.keys()),
        changed=changed,
        build_changed=old.get("buildid") != new.get("buildid"),
    )


# --- 에셋 목록(manifest) ------------------------------------------------------

# 게임 루트의 manifest: "<에셋 경로>,<아카이브>,<오프셋>,<크기>" 한 줄에 하나.
# 아래 패턴은 build 24237529 의 manifest 에서 직접 확인한 것이다 (docs/modding-tools.md).
ASSET_PATTERNS: dict[str, re.Pattern[str]] = {
    "face": re.compile(r"char/sig/png(\d+)\.iff"),
    "portrait": re.compile(r"player_images/chr_g(\d+)\.iff"),
    "logo": re.compile(r"logos/logo(\d+)\.iff"),
    "court": re.compile(r"levels/arena_(\d+)_int_floor\.iff"),
    "uniform": re.compile(r"frontend_uniforms/u(\d+)([a-z]+)_\d+_(?:home|away)\.iff"),
    "expansion_uniform": re.compile(r"frontend_uniforms/expansion(\d+)_(?:home|away)\.iff"),
}


def read_asset_manifest(game_dir: Path) -> list[str]:
    path = Path(game_dir) / "manifest"
    if not path.is_file():
        raise GameError(f"에셋 manifest 가 없습니다: {path}")
    names = []
    with path.open("rb") as f:
        for raw in f:
            parts = raw.decode("utf-8", "replace").strip().split(",")
            if len(parts) == 4:
                names.append(parts[0].lower())
    return names


def asset_summary(names: list[str]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for kind, pat in ASSET_PATTERNS.items():
        ids = sorted({int(m.group(1)) for n in names if (m := pat.fullmatch(n))})
        out[kind] = {
            "count": len(ids),
            "min": ids[0] if ids else None,
            "max": ids[-1] if ids else None,
        }
    return out
