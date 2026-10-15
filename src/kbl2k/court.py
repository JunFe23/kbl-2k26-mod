"""코트 바닥 텍스처 합성 (ADR-0019).

OzWolf 코트 템플릿(court_floor.psd)의 레이어를 PNG 로 꺼낸 폴더를 입력으로 받는다.
레이어는 8192×4096 캔버스 좌표 그대로다. 각 레이어의 알파를 마스크로 써서 팀 색을 칠하고,
로고·글자를 얹은 뒤 템플릿의 질감(그림자·긁힘·요철)을 덮는다.

템플릿·결과 이미지는 저장소에 넣지 않는다(상표·2K 에셋 파생물). 디자인 값만 data/ 에 둔다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .assets import AssetError, _pil

W, H = 8192, 4096
CENTER = (W // 2, H // 2)

# 템플릿 레이어 파일 이름(extract 결과) — 역할별
LAYER_WOOD = "Court_Floors_Full_Floor_1"
LAYER_OUTSIDE = "Outside_Color"
LAYER_KEY = "Keys_Full_Key"
LAYER_KEY_CIRCLE = "Keys_Full_Circle"
# 템플릿 'Center Line' 은 psd-tools 로 렌더링되지 않는다(빈 레이어) → 직접 그린다.
# 위치·굵기는 Out of Bounds 선에서 잰 값: 선 굵기 10px, 코트 위·아래 끝 y 438~3659.
CENTER_LINE_BOX = (4092, 438, 4101, 3659)
LINE_LAYERS = (
    "Lines_3_point_lines",
    "Lines_Hash_Lines",
    "Lines_Media_Boxes",
    "Lines_Inner_Key_Lines",
    "Lines_Key_Dashed_Lines",
    "Lines_Key_Lines",
    "Lines_Half_Court_Circles",
    "Lines_Out_of_Bounds",
    "Lines_Charge_Circles",
)
DETAIL_LAYERS = (  # (레이어, 추가 불투명도) — 추출 PNG 에 레이어 불투명도가 이미 반영됨
    ("Details_Shadows_1", 1.0),
    ("Details_Scratched_floor", 1.0),
    ("Details_Floor_Bump", 1.0),
)
# 글자 자리 (템플릿 Sideline/Baseline Text 레이어 위치)
SIDELINE_BOXES = ((973, 267, 2262, 455), (5883, 267, 7223, 455))
BASELINE_BOXES = ((618, 378, 904, 3726), (7293, 370, 7578, 3718))


def _layer(layers: Path, name: str):
    p = layers / f"{name}.png"
    if not p.is_file():
        raise AssetError(f"템플릿 레이어가 없습니다: {p}")
    return _pil().open(p).convert("RGBA")


def _rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _paint(base, mask_layer, color: str, opacity: float = 1.0):
    """mask_layer 의 알파 모양대로 color 를 칠한다."""
    Image = _pil()
    alpha = mask_layer.getchannel("A")
    if opacity < 1:
        alpha = alpha.point(lambda v: round(v * opacity))
    fill = Image.new("RGBA", base.size, (*_rgb(color), 255))
    fill.putalpha(alpha)
    base.alpha_composite(fill)


def _font(size: int, path: str):
    from PIL import ImageFont

    try:
        return ImageFont.truetype(path, size)
    except OSError as e:
        raise AssetError(f"글꼴을 열 수 없습니다: {path}") from e


def _text_in_box(base, box, text: str, color: str, font_path: str, vertical: bool, flip: bool):
    """box 안에 꽉 차게 글자를 쓴다. vertical 이면 90° 돌린다(flip 이면 반대 방향)."""
    Image = _pil()
    from PIL import ImageDraw

    x0, y0, x1, y1 = box
    bw, bh = x1 - x0, y1 - y0
    long_side, short_side = (bh, bw) if vertical else (bw, bh)
    size = int(short_side * 0.8)
    font = _font(size, font_path)
    x0b, t, r, b = font.getbbox(text)
    if r - x0b > long_side * 0.95:
        size = int(size * long_side * 0.95 / (r - x0b))
        font = _font(size, font_path)
        x0b, t, r, b = font.getbbox(text)
    img = Image.new("RGBA", (r - x0b, b - t), (0, 0, 0, 0))
    ImageDraw.Draw(img).text((-x0b, -t), text, font=font, fill=(*_rgb(color), 255))
    if vertical:
        img = img.rotate(-90 if flip else 90, expand=True)
    base.alpha_composite(img, (x0 + (bw - img.width) // 2, y0 + (bh - img.height) // 2))


def _logo(base, path: Path, diameter: int, at: tuple[int, int], opacity: float = 1.0):
    Image = _pil()
    logo = Image.open(path).convert("RGBA")
    bbox = logo.getbbox()
    if bbox:
        logo = logo.crop(bbox)
    s = diameter / max(logo.size)
    logo = logo.resize((round(logo.width * s), round(logo.height * s)), Image.LANCZOS)
    if opacity < 1:
        logo.putalpha(logo.getchannel("A").point(lambda v: round(v * opacity)))
    base.alpha_composite(logo, (at[0] - logo.width // 2, at[1] - logo.height // 2))


def make_court(layers: Path, design: dict[str, Any], dst: Path, logo: Path | None = None) -> dict:
    """design 예:
    {"apron": "#C8102E", "key": "#C8102E", "key_circle": null, "lines": "#FFFFFF",
     "center_logo_diameter": 1300, "sideline_text": ["ANYANG CITY", "ANYANG CITY"],
     "baseline_text": ["RED BOOSTERS", "RED BOOSTERS"], "text_color": "#FFFFFF",
     "font": "C:/Windows/Fonts/ariblk.ttf"}
    """
    layers, dst = Path(layers), Path(dst)
    base = _layer(layers, LAYER_WOOD)
    if base.size != (W, H):
        raise AssetError(f"템플릿 크기가 예상(8192×4096)과 다릅니다: {base.size}")
    base.putalpha(255)
    _paint(base, _layer(layers, LAYER_OUTSIDE), design["apron"])
    if design.get("key"):
        _paint(base, _layer(layers, LAYER_KEY), design["key"])
    if design.get("key_circle"):
        _paint(base, _layer(layers, LAYER_KEY_CIRCLE), design["key_circle"])
    for name in LINE_LAYERS:
        _paint(base, _layer(layers, name), design.get("lines", "#FFFFFF"))
    from PIL import ImageDraw

    ImageDraw.Draw(base).rectangle(
        CENTER_LINE_BOX, fill=(*_rgb(design.get("lines", "#FFFFFF")), 255)
    )
    # 로고는 선 위에 얹는다(실제 코트처럼 중앙선·센터서클이 로고 아래로 지나감)
    if logo and design.get("center_logo_diameter"):
        _logo(
            base, logo, design["center_logo_diameter"], CENTER, design.get("center_logo_opacity", 1)
        )
    font = design.get("font", "C:/Windows/Fonts/ariblk.ttf")
    color = design.get("text_color", "#FFFFFF")
    for box, text in zip(SIDELINE_BOXES, design.get("sideline_text", []), strict=False):
        if text:
            _text_in_box(base, box, text, color, font, vertical=False, flip=False)
    for i, (box, text) in enumerate(
        zip(BASELINE_BOXES, design.get("baseline_text", []), strict=False)
    ):
        if text:
            _text_in_box(base, box, text, color, font, vertical=True, flip=i == 1)
    for name, opacity in DETAIL_LAYERS:
        detail = _layer(layers, name)
        if opacity < 1:
            detail.putalpha(detail.getchannel("A").point(lambda v, o=opacity: round(v * o)))
        base.alpha_composite(detail)
    out = base.convert("RGB")
    dst.parent.mkdir(parents=True, exist_ok=True)
    out.save(dst, "PNG")
    out.resize((2048, 1024)).save(dst.with_name(dst.stem + "_preview.png"))
    return {"dst": str(dst), "size": out.size}
