"""로고 변환 테스트 (합성 이미지, 실제 구단 로고 사용 안 함)."""

import pytest

PIL = pytest.importorskip("PIL")
from PIL import Image, ImageDraw  # noqa: E402

from kbl2k.assets import fill_gaps, fit_square, make_logo, remove_outer_background  # noqa: E402


def synthetic_logo():
    """흰 바탕 위 빨간 사각형 + 그 안에 완전히 둘러싸인 흰 구멍 + 바깥과 이어진 흰 틈."""
    im = Image.new("RGB", (200, 300), (255, 255, 255))
    d = ImageDraw.Draw(im)
    d.rectangle((40, 40, 160, 260), fill=(220, 30, 40))
    d.rectangle((80, 120, 120, 160), fill=(255, 255, 255))  # 둘러싸인 흰 구멍
    d.rectangle((95, 40, 105, 100), fill=(255, 255, 255))  # 위쪽 가장자리와 이어진 흰 틈
    return im


def test_outer_background_removed_but_enclosed_white_kept():
    out = remove_outer_background(synthetic_logo())
    a = out.getchannel("A")
    assert a.getpixel((5, 5)) == 0  # 바깥 배경 투명
    assert a.getpixel((100, 140)) == 255  # 둘러싸인 흰 구멍은 유지
    assert a.getpixel((100, 200)) == 255  # 로고 본체
    assert a.getpixel((100, 70)) == 0  # 바깥과 이어진 틈은 일단 투명


def test_fill_gaps_restores_white_gap_inside_silhouette():
    out = fill_gaps(remove_outer_background(synthetic_logo()), radius=10)
    assert out.getpixel((100, 70))[3] == 255 and out.getpixel((100, 70))[:3] == (255, 255, 255)
    assert out.getpixel((5, 5))[3] == 0


def test_fit_square_centers_with_margin():
    out = fit_square(remove_outer_background(synthetic_logo()), size=256, margin=0.1)
    assert out.size == (256, 256)
    x0, y0, x1, y1 = out.getbbox()
    assert y1 - y0 == round(256 * 0.8) and (x0 + x1) // 2 in (127, 128)


def test_make_logo_png_and_svg(tmp_path):
    src = tmp_path / "logo.jpg"
    synthetic_logo().save(src, "JPEG", quality=95)
    r = make_logo(src, tmp_path / "out.png", size=128)
    assert r["size"] == (128, 128) and "gaps-filled" in r["method"]

    pytest.importorskip("resvg_py")
    svg = tmp_path / "logo.svg"
    svg.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="50">'
        '<rect x="10" y="10" width="80" height="30" fill="red"/></svg>',
        "utf-8",
    )
    r = make_logo(svg, tmp_path / "svg.png", size=128)
    im = Image.open(tmp_path / "svg.png")
    assert r["method"] == "svg-render" and im.getpixel((0, 0))[3] == 0
