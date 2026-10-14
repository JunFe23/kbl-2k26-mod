import pytest

from kbl2k.backup import (
    MANIFEST,
    BackupError,
    create_backup,
    read_manifest,
    restore_backup,
    sha256_file,
    verify_backup,
)


@pytest.fixture
def game(tmp_path):
    g = tmp_path / "NBA 2K26"
    (g / "sub").mkdir(parents=True)
    (g / "a.bin").write_bytes(b"original-a")
    (g / "sub" / "b.bin").write_bytes(b"original-b" * 1000)
    return g


@pytest.fixture
def backup(game, tmp_path):
    return create_backup(game, ["a.bin", "sub/b.bin"], tmp_path / "backups", "pre-mod")


def test_backup_writes_manifest_and_copies(game, backup):
    m = read_manifest(backup)
    assert [e["path"] for e in m["files"]] == ["a.bin", "sub/b.bin"]
    assert m["files"][0]["sha256"] == sha256_file(game / "a.bin")
    assert (backup / "files" / "sub" / "b.bin").read_bytes() == (
        game / "sub" / "b.bin"
    ).read_bytes()
    assert backup.name.endswith("pre-mod")
    assert verify_backup(backup) == []


def test_backup_does_not_touch_game_dir(game, tmp_path):
    before = {p: p.stat().st_mtime_ns for p in game.rglob("*")}
    create_backup(game, ["a.bin"], tmp_path / "backups")
    assert {p: p.stat().st_mtime_ns for p in game.rglob("*")} == before


def test_backup_names_unique(game, tmp_path):
    a = create_backup(game, ["a.bin"], tmp_path / "bk", "x")
    b = create_backup(game, ["a.bin"], tmp_path / "bk", "x")
    assert a != b


@pytest.mark.parametrize("bad", ["../escape.bin", "/abs.bin", "C:/abs.bin", "sub/../../x"])
def test_rejects_unsafe_paths(game, tmp_path, bad):
    with pytest.raises(BackupError):
        create_backup(game, [bad], tmp_path / "bk")


def test_rejects_backup_inside_game_dir(game):
    with pytest.raises(BackupError, match="밖"):
        create_backup(game, ["a.bin"], game / "backup")


def test_rejects_missing_file(game, tmp_path):
    with pytest.raises(BackupError, match="없습니다"):
        create_backup(game, ["nope.bin"], tmp_path / "bk")


def test_rejects_empty_file_list(game, tmp_path):
    with pytest.raises(BackupError):
        create_backup(game, [], tmp_path / "bk")


def test_restore_dry_run_does_not_write(game, backup):
    (game / "a.bin").write_bytes(b"modded")
    steps = restore_backup(backup, game)
    assert {s.path: s.action for s in steps} == {"a.bin": "restore", "sub/b.bin": "unchanged"}
    assert (game / "a.bin").read_bytes() == b"modded"


def test_restore_apply_round_trip(game, backup):
    (game / "a.bin").write_bytes(b"modded")
    (game / "sub" / "b.bin").unlink()
    steps = restore_backup(backup, game, apply=True)
    assert {s.action for s in steps} == {"restore", "create"}
    assert (game / "a.bin").read_bytes() == b"original-a"
    assert (game / "sub" / "b.bin").read_bytes() == b"original-b" * 1000


def test_restore_refuses_corrupt_backup(game, backup):
    (backup / "files" / "a.bin").write_bytes(b"corrupt")
    assert verify_backup(backup) == ["해시 불일치: a.bin"]
    (game / "a.bin").write_bytes(b"modded")
    with pytest.raises(BackupError, match="손상"):
        restore_backup(backup, game, apply=True)
    assert (game / "a.bin").read_bytes() == b"modded"


def test_restore_refuses_other_game_dir_without_force(game, backup, tmp_path):
    other = tmp_path / "other"
    other.mkdir()
    with pytest.raises(BackupError, match="force"):
        restore_backup(backup, other)
    steps = restore_backup(backup, other, force=True)
    assert all(s.action == "create" for s in steps)


def test_missing_manifest(tmp_path):
    with pytest.raises(BackupError, match=MANIFEST):
        verify_backup(tmp_path)
