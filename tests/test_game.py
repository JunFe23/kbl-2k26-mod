"""게임 정보·스냅샷 테스트 (가짜 Steam 폴더 사용, 실제 게임 폴더 접근 안 함)."""

import json
import os

import pytest

from kbl2k.cli import main
from kbl2k.game import (
    GameError,
    asset_summary,
    diff_snapshots,
    find_game,
    library_paths,
    parse_vdf_pairs,
    read_asset_manifest,
    save_snapshot,
    take_snapshot,
)

ACF = """"AppState"
{
\t"appid"\t\t"3472040"
\t"name"\t\t"NBA 2K26"
\t"installdir"\t\t"NBA 2K26"
\t"LastUpdated"\t\t"1786746250"
\t"buildid"\t\t"24237529"
}
"""

MANIFEST = "\n".join([
    "char/sig/png1234.iff,0C,0,10",
    "char/sig/png1234_geo_hair_1.iff,0C,10,10",
    "char/sig/png35.iff,0C,20,10",
    "logos/logo7.iff,0A,0,5",
    "logos/logo7_wm.iff,0A,5,5",
    "levels/arena_12_int_floor.iff,0B,0,5",
    "frontend_uniforms/u930bos_1_home.iff,0B,5,5",
    "frontend_uniforms/expansion3_away.iff,0B,10,5",
    "player_images/chr_g110.iff,0B,15,5",
    "garbage line",
])  # fmt: skip


@pytest.fixture
def steam(tmp_path):
    """Steam 폴더 + 별도 라이브러리에 설치된 가짜 게임."""
    steam = tmp_path / "steam"
    lib = tmp_path / "lib2"
    (steam / "steamapps").mkdir(parents=True)
    (lib / "steamapps" / "common" / "NBA 2K26" / "data").mkdir(parents=True)
    vdf_lib = str(lib).replace("\\", "\\\\")
    (steam / "steamapps" / "libraryfolders.vdf").write_text(
        f'"libraryfolders"\n{{\n "0"\n {{\n  "path" "{vdf_lib}"\n }}\n}}\n', "utf-8"
    )
    (lib / "steamapps" / "appmanifest_3472040.acf").write_text(ACF, "utf-8")
    game = lib / "steamapps" / "common" / "NBA 2K26"
    (game / "manifest").write_text(MANIFEST, "utf-8")
    (game / "NBA2K26.exe").write_bytes(b"exe")
    (game / "data" / "x.dll").write_bytes(b"dll")
    return steam, game


def test_parse_vdf_pairs_unescapes_backslashes():
    assert parse_vdf_pairs('"path"\t\t"E:\\\\game\\\\steam"') == [("path", "E:\\game\\steam")]


def test_library_paths_includes_steam_and_extra(steam):
    s, game = steam
    libs = library_paths(s)
    assert libs[0] == s and len(libs) == 2


def test_find_game(steam):
    s, game = steam
    info = find_game(s)
    assert info.name == "NBA 2K26" and info.buildid == "24237529"
    assert info.install_dir == game
    assert info.last_updated is not None


def test_find_game_missing(tmp_path):
    (tmp_path / "steamapps").mkdir()
    with pytest.raises(GameError, match="appid"):
        find_game(tmp_path)


def test_asset_summary(steam):
    _, game = steam
    s = asset_summary(read_asset_manifest(game))
    assert s["face"] == {"count": 2, "min": 35, "max": 1234}
    assert s["logo"]["count"] == 1
    assert s["court"]["min"] == 12
    assert s["uniform"]["max"] == 930
    assert s["expansion_uniform"]["count"] == 1
    assert s["portrait"]["min"] == 110


def test_missing_asset_manifest(tmp_path):
    with pytest.raises(GameError, match="manifest"):
        read_asset_manifest(tmp_path)


def test_snapshot_and_diff(steam):
    _, game = steam
    before = take_snapshot(game, "1")
    assert set(before["files"]) == {"manifest", "NBA2K26.exe", "data/x.dll"}
    assert "sha256" in before["files"]["NBA2K26.exe"]

    (game / "NBA2K26.exe").write_bytes(b"patched")
    (game / "data" / "x.dll").unlink()
    (game / "mods").mkdir()
    (game / "mods" / "new.iff").write_bytes(b"m")
    d = diff_snapshots(before, take_snapshot(game, "1"))
    assert d.added == ["mods/new.iff"]
    assert d.removed == ["data/x.dll"]
    assert d.changed == ["NBA2K26.exe"]
    assert not d.build_changed and not d.clean


def test_large_files_compared_by_mtime(steam):
    _, game = steam
    before = take_snapshot(game, "1", hash_limit=0)
    assert "sha256" not in before["files"]["manifest"]
    assert diff_snapshots(before, take_snapshot(game, "1", hash_limit=0)).clean
    st = (game / "manifest").stat()
    os.utime(game / "manifest", ns=(st.st_atime_ns, st.st_mtime_ns + 10**9))
    assert diff_snapshots(before, take_snapshot(game, "1", hash_limit=0)).changed == ["manifest"]


def test_build_change_detected(steam):
    _, game = steam
    a = take_snapshot(game, "1")
    assert diff_snapshots(a, {**a, "buildid": "2"}).build_changed


def test_snapshot_does_not_modify_game(steam):
    _, game = steam
    before = {p: p.stat().st_mtime_ns for p in game.rglob("*")}
    take_snapshot(game)
    assert {p: p.stat().st_mtime_ns for p in game.rglob("*")} == before


def test_save_snapshot_refuses_inside_game_dir(steam, tmp_path):
    _, game = steam
    snap = take_snapshot(game)
    with pytest.raises(GameError, match="밖"):
        save_snapshot(snap, game / "snaps")
    path = save_snapshot(snap, tmp_path / "snaps", "x")
    assert json.loads(path.read_text("utf-8"))["files"]
    assert save_snapshot(snap, tmp_path / "snaps", "x") != path


def test_cli_game_info_and_diff(capsys, steam, tmp_path):
    s, game = steam
    assert main(["game", "--steam-dir", str(s), "info"]) == 0
    out = capsys.readouterr().out
    assert "24237529" in out and "face" in out

    snaps = tmp_path / "snaps"
    assert main(["game", "--steam-dir", str(s), "snapshot", "--out", str(snaps)]) == 0
    snap = next(snaps.iterdir())
    capsys.readouterr()
    assert main(["game", "--steam-dir", str(s), "diff", str(snap)]) == 0
    assert "변경 없음" in capsys.readouterr().out
    (game / "mods").mkdir()
    (game / "mods" / "a.iff").write_bytes(b"x")
    assert main(["game", "--steam-dir", str(s), "diff", str(snap)]) == 2
    assert "추가  mods/a.iff" in capsys.readouterr().out


def test_cli_game_info_error(capsys, tmp_path):
    (tmp_path / "steamapps").mkdir()
    assert main(["game", "--steam-dir", str(tmp_path), "info"]) == 1
