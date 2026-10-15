"""로고 이미지 → 게임용 투명 정사각 PNG (ADR-0019).

- JPG/PNG: 가장자리에서 이어진 바깥 배경만 투명하게 만든다(로고 안의 흰 부분은 유지).
  경계는 배경색과의 거리로 알파를 부드럽게 준다.
- SVG: 투명 배경으로 렌더링한다(resvg).
- 결과는 size×size 정사각형 가운데에 여백(margin 비율)을 두고 배치한다.

Pillow·resvg-py 는 선택 의존성이다: pip install -e ".[assets]"
"""

from __future__ import annotations

import io
from collections import deque
from pathlib import Path

DEFAULT_SIZE = 1024
DEFAULT_MARGIN = 0.06


class AssetError(Exception):
    pass


def _pil():
    try:
        from PIL import Image
    except ImportError as e:  # pragma: no cover
        raise AssetError('Pillow 가 필요합니다: pip install -e ".[assets]"') from e
    return Image


def render_svg(path: Path, height: int = 2048):
    Image = _pil()
    try:
        import resvg_py
    except ImportError as e:  # pragma: no cover
        raise AssetError('resvg-py 가 필요합니다: pip install -e ".[assets]"') from e
    png = resvg_py.svg_to_bytes(svg_path=str(path), height=height)
    return Image.open(io.BytesIO(bytes(png))).convert("RGBA")


def remove_outer_background(img, tolerance: int = 40, soft: int = 40):
    """가장자리와 이어진 배경색 영역을 투명하게. 배경색은 네 모서리의 평균."""
    Image = _pil()
    img = img.convert("RGBA")
    w, h = img.size
    px = img.load()
    corners = [px[0, 0], px[w - 1, 0], px[0, h - 1], px[w - 1, h - 1]]
    bg = tuple(sum(c[i] for c in corners) // 4 for i in range(3))

    def dist(c) -> int:
        return max(abs(c[0] - bg[0]), abs(c[1] - bg[1]), abs(c[2] - bg[2]))

    limit = tolerance + soft
    seen = bytearray(w * h)
    q: deque[tuple[int, int]] = deque()
    for x in range(w):
        q.extend(((x, 0), (x, h - 1)))
    for y in range(h):
        q.extend(((0, y), (w - 1, y)))
    alpha = Image.new("L", (w, h), 255)
    a = alpha.load()
    while q:
        x, y = q.popleft()
        i = y * w + x
        if seen[i]:
            continue
        seen[i] = 1
        d = dist(px[x, y])
        if d > limit:
            continue  # 로고 경계 — 더 들어가지 않는다
        a[x, y] = 0 if d <= tolerance else round(255 * (d - tolerance) / soft)
        if d <= tolerance:
            for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if 0 <= nx < w and 0 <= ny < h and not seen[ny * w + nx]:
                    q.append((nx, ny))
    img.putalpha(alpha)
    return img


def fill_gaps(img, radius: int, color=(255, 255, 255)):
    """로고 외곽 실루엣(닫힘 연산) 안의 투명 틈을 color 로 채운다.

    흰 바탕 전제로 디자인된 로고에서 글자·도형 사이 흰 틈이 배경과 함께 뚫리는 것을 막는다.
    """
    Image = _pil()
    from PIL import ImageFilter

    a = img.getchannel("A").point(lambda v: 255 if v > 0 else 0)
    k = radius * 2 + 1
    silhouette = a.filter(ImageFilter.MaxFilter(k)).filter(ImageFilter.MinFilter(k))
    under = Image.new("RGBA", img.size, (*color, 0))
    under.putalpha(silhouette)
    under.alpha_composite(img)
    return under


def fit_square(img, size: int = DEFAULT_SIZE, margin: float = DEFAULT_MARGIN):
    """투명 여백을 잘라내고 size×size 가운데에 비율 유지로 배치."""
    Image = _pil()
    bbox = img.getbbox()
    if bbox is None:
        raise AssetError("이미지가 비어 있습니다(전부 투명)")
    img = img.crop(bbox)
    inner = round(size * (1 - 2 * margin))
    scale = inner / max(img.size)
    img = img.resize((max(1, round(img.width * scale)), max(1, round(img.height * scale))),
                     Image.LANCZOS)  # fmt: skip
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas.paste(img, ((size - img.width) // 2, (size - img.height) // 2), img)
    return canvas


def make_logo(
    src: Path,
    dst: Path,
    size: int = DEFAULT_SIZE,
    margin: float = DEFAULT_MARGIN,
    gap_radius: int | None = None,
) -> dict:
    src, dst = Path(src), Path(dst)
    if not src.is_file():
        raise AssetError(f"파일이 없습니다: {src}")
    if src.suffix.lower() == ".svg":
        img = render_svg(src)
        method = "svg-render"
    else:
        img = _pil().open(src)
        has_alpha = img.mode in ("RGBA", "LA") and img.getextrema()[-1][0] < 255
        img = img.convert("RGBA") if has_alpha else remove_outer_background(img)
        method = "keep-alpha" if has_alpha else "outer-background-removed"
        if not has_alpha:
            r = gap_radius if gap_radius is not None else max(3, round(max(img.size) * 0.03))
            if r > 0:
                img = fill_gaps(img, r)
                method += f"+gaps-filled(r={r})"
    out = fit_square(img, size, margin)
    dst.parent.mkdir(parents=True, exist_ok=True)
    out.save(dst, "PNG")
    return {"src": str(src), "dst": str(dst), "size": out.size, "method": method}
