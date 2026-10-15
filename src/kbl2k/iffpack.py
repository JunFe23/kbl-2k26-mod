"""원본 IFF(ZIP)에 교체 텍스처 DDS 를 넣어 mods 용 IFF 를 만든다 (ADR-0019·0020).

검증된 원리(CustomMyNBA 로고·코트·유니폼): IFF 안의 TXTR 는 그대로 두고,
TXTR 의 Binary 이름 "<이름>.<해시>.tld" 와 같은 이름의 "<이름>.<해시>.dds" 를 함께 넣으면
게임이 스트리밍 데이터 대신 그 DDS 를 읽는다.
DDS 는 Microsoft texconv 로 만든다(BC7, 전체 mip).
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

from .assets import AssetError

BINARY_RE = re.compile(rb"([A-Za-z0-9_]+\.[0-9a-f]{16})\.tld")


def txtr_binary_stem(txtr: bytes) -> str:
    """TXTR(텍스트·바이너리 모두) 안의 "<이름>.<해시>.tld" → "<이름>.<해시>"."""
    m = BINARY_RE.search(txtr)
    if not m:
        raise AssetError("TXTR 에서 Binary(.tld) 이름을 찾지 못했습니다")
    return m.group(1).decode("ascii")


def png_to_dds(png: Path, texconv: Path, fmt: str = "BC7_UNORM") -> bytes:
    if not Path(texconv).is_file():
        raise AssetError(f"texconv 가 없습니다: {texconv}")
    with tempfile.TemporaryDirectory() as td:
        src = Path(td) / "tex.png"
        shutil.copyfile(png, src)
        r = subprocess.run(
            [str(texconv), "-nologo", "-y", "-f", fmt, "-m", "0", "-o", td, str(src)],
            capture_output=True,
            text=True,
        )
        out = Path(td) / "tex.dds"
        if r.returncode != 0 or not out.is_file():
            raise AssetError(f"texconv 실패: {r.stdout[-300:]} {r.stderr[-300:]}")
        return out.read_bytes()


def build_iff(src_iff: Path, replacements: dict[str, bytes], dst_iff: Path) -> list[str]:
    """src_iff 를 복사하면서 {TXTR 이름: DDS 바이트} 를 '<Binary 이름>.dds' 로 추가한다."""
    added = []
    with zipfile.ZipFile(src_iff) as zin:
        names = zin.namelist()
        for t in replacements:
            if t not in names:
                raise AssetError(f"IFF 에 {t} 가 없습니다")
        dst_iff = Path(dst_iff)
        dst_iff.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(dst_iff, "w", zipfile.ZIP_DEFLATED) as zout:
            for n in names:
                zout.writestr(zin.getinfo(n), zin.read(n))
            for t, dds in replacements.items():
                name = txtr_binary_stem(zin.read(t)) + ".dds"
                if name in names:
                    raise AssetError(f"이미 같은 DDS 가 있습니다: {name}")
                zout.writestr(name, dds)
                added.append(name)
    return added
