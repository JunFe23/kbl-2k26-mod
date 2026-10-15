"""코트 합성 보조 함수 테스트 (작은 합성 이미지, 템플릿 없이)."""

import pytest

PIL = pytest.importorskip("PIL")
from PIL import Image  # noqa: E402

from kbl2k.assets import AssetError  # noqa: E402
from kbl2k.court import _paint, _text_in_box, make_court  # noqa: E402

FONT = "C:/Windows/Fonts/arialbd.ttf"


def test_paint_uses_mask_alpha():
    base = Image.new("RGBA", (10, 10), (0, 0, 0, 255))
    mask = Image.new("RGBA", (10, 10), (0, 0, 0, 0))
    mask.putpixel((2, 2), (255, 255, 255, 255))
    _paint(base, mask, "#C8102E")
    assert base.getpixel((2, 2))[:3] == (200, 16, 46)
    assert base.getpixel((5, 5))[:3] == (0, 0, 0)


def test_text_stays_inside_box():
    try:
        base = Image.new("RGBA", (400, 400), (0, 0, 0, 0))
        _text_in_box(base, (50, 20, 350, 60), "ANYANG CITY", "#FFFFFF", FONT, False, False)
        vbase = Image.new("RGBA", (400, 400), (0, 0, 0, 0))
        _text_in_box(vbase, (10, 50, 50, 350), "RED BOOSTERS", "#FFFFFF", FONT, True, False)
    except AssetError:
        pytest.skip("글꼴 없음")
    x0, y0, x1, y1 = base.getbbox()
    assert x0 >= 50 and x1 <= 350 and y0 >= 20 and y1 <= 60
    x0, y0, x1, y1 = vbase.getbbox()
    assert x0 >= 10 and x1 <= 50 and y1 - y0 > x1 - x0  # 세로로 섰다


def test_make_court_requires_layers(tmp_path):
    with pytest.raises(AssetError):
        make_court(tmp_path, {"apron": "#000000"}, tmp_path / "out.png")
