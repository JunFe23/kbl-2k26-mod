"""유니폼 전개도 그림 생성 (ADR-0019, CustomMyNBA 방식).

CustomMyNBA 템플릿(uniform.psd, 4096×4096)의 전개도에 실제 유니폼 사진을 옮긴다.
  - 앞판 x 1946~3500, 옆판 R(선수 오른쪽) x 1589~1946, L x 3500~3856 (겨드랑이 y 1164 아래)
  - 뒤판은 뒤에서 볼 때 왼쪽부터 x 3856→4096, 0→1589 로 이어진다
  - 저지 y 0(목) ~ 2493, 허리띠 2493~2655, 반바지 2655~3908, 밑단 3908~4096
  게임 안 보정 시험(격자)으로 확인한 배치다.

사진 처리
  1. 사진 영역을 팔레트 색으로 분류한다(검정·빨강·흰색 등).
  2. 번호·이름·글자 같은 '잉크' 색과 사진 배경은 가장 가까운 바탕색으로 메운다 → 바탕 무늬만 남는다.
  3. 색별 마스크를 전개도 좌표로 옮겨(쌍선형) 가장 강한 색을 고른다 → 경계가 매끈하다.
  4. 글자·스폰서는 사진의 해당 상자에서 색 마스크를 따서 같은 좌표로 옮겨 얹는다.
  5. 옆판·허리띠·반바지는 설정값으로 그린다.

사진·결과 이미지는 저장소에 넣지 않는다(assets_private/). 설정만 data/visuals/uniforms.json.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .assets import AssetError, _pil

S = 4096
FRONT = (1946, 3500)
SIDE_R = (1589, 1946)
SIDE_L = (3500, 3856)
BACK_WIDTH = (4096 - 3856) + 1589  # 1829
# 뒤판 가운데 = 등번호 중심 x≈835 (게임 확인, 템플릿 뒤 목 NBA 로고 위치와 같다).
# 뒤판 그림은 L 옆판 끝(3856)부터 R 옆판 안쪽(1749)까지 넓게 그린다(넘친 부분은 옆판이 덮음).
# 사진의 등 가운데(cfg center_x)가 835 에 오고, 가로 배율은 사진 옆선 간격으로 정한다.
BACK_CENTER = 835
BACK_START = 3856
BACK_RENDER = (4096 - BACK_START) + 1749
JERSEY_BOTTOM = 2493
ARMPIT = 1164
BELT = (2493, 2655)
SHORTS = (2655, 3908)


def _np():
    try:
        import numpy as np
        from scipy import ndimage
    except ImportError as e:  # pragma: no cover
        raise AssetError("numpy·scipy 가 필요합니다: pip install numpy scipy") from e
    return np, ndimage


def _rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def classify(photo, palette: dict[str, str]):
    """사진(H×W×3) → 팔레트 이름 인덱스(H×W). 가장 가까운 색."""
    np, _ = _np()
    cols = np.array([_rgb(c) for c in palette.values()], dtype=np.float32)
    d = ((photo[:, :, None, :].astype(np.float32) - cols[None, None]) ** 2).sum(-1)
    return d.argmin(-1)


def fill_from_nearest(labels, bad):
    """bad(True) 자리를 가장 가까운 정상 픽셀의 라벨로 채운다."""
    np, nd = _np()
    if not bad.any():
        return labels
    idx = nd.distance_transform_edt(bad, return_distances=False, return_indices=True)
    return labels[tuple(idx)]


class Panel:
    """사진의 한 면(앞/뒤) → 전개도 좌표 변환.

    가로: u = (x - x0) * su (옆선 간격으로 배율, center_x 가 있으면 그 점이 center_u 에 온다)
    세로: anchors [[사진 y, 전개도 v], ...] 두 점 이상을 구간별 선형으로 잇는다(양 끝은 연장).
    """

    def __init__(self, cfg: dict[str, Any], width: int, center_u: float | None = None):
        self.x0, self.x1 = cfg["seams"]
        self.su = cfg.get("seam_width_uv", width) / (self.x1 - self.x0)
        if center_u is not None and "center_x" in cfg:
            self.x0 = cfg["center_x"] - center_u / self.su
        pts = sorted(cfg["anchors"])
        if len(pts) < 2:
            raise AssetError("anchors 는 두 점 이상이어야 합니다")
        self.ys = [float(a) for a, _ in pts]
        self.vs = [float(b) for _, b in pts]
        self.width = width

    @staticmethod
    def _interp(x, xs, ys):
        np, _ = _np()
        x = np.asarray(x, dtype=np.float64)
        out = np.interp(x, xs, ys)
        lo = (ys[1] - ys[0]) / (xs[1] - xs[0])
        hi = (ys[-1] - ys[-2]) / (xs[-1] - xs[-2])
        out = np.where(x < xs[0], ys[0] + (x - xs[0]) * lo, out)
        return np.where(x > xs[-1], ys[-1] + (x - xs[-1]) * hi, out)

    def to_photo(self, u, v):
        return self.x0 + u / self.su, self._interp(v, self.vs, self.ys)

    def y_to_v(self, y):
        return float(self._interp(y, self.ys, self.vs))

    def box_to_uv(self, box):
        x0, y0, x1, y1 = box
        return (
            (x0 - self.x0) * self.su,
            self.y_to_v(y0),
            (x1 - self.x0) * self.su,
            self.y_to_v(y1),
        )


def _render_panel(
    photo, cfg: dict[str, Any], palette: dict[str, str], width: int, center_u: float | None = None
):
    """사진 한 면 → width × JERSEY_BOTTOM RGBA (바탕 무늬 + 얹을 것)."""
    np, nd = _np()
    names = list(palette)
    labels = classify(photo, palette)
    bad = np.isin(labels, [names.index(n) for n in cfg.get("fill", [])])
    for box in cfg.get("erase", []):  # 번호·이름 등 게임이 그리는 자리
        x0, y0, x1, y1 = box
        bad[y0:y1, x0:x1] = True
    # 다시 얹을 글자·로고는 원래 자리에서 가장자리(안티에일리어싱)까지 넓혀 지운다
    for ov in cfg.get("overlays", []):
        x0, y0, x1, y1 = ov["box"]
        sel = np.array(_rgb(ov["select"]), dtype=np.float32)
        dist = np.sqrt(((photo[y0:y1, x0:x1].astype(np.float32) - sel) ** 2).sum(-1))
        tol = float(ov.get("tol", 90))
        near = dist > tol if ov.get("mode") == "photo" else dist < tol * 1.6
        ink = nd.binary_dilation(near, iterations=3)
        bad[y0:y1, x0:x1] |= ink
    labels = fill_from_nearest(labels, bad)

    panel = Panel(cfg, width, center_u)
    vv, uu = np.mgrid[0:JERSEY_BOTTOM, 0:width].astype(np.float32)
    px, py = panel.to_photo(uu, vv)
    sx0, sx1 = cfg["seams"]  # 옆선 바깥(사진 속 옆판)은 읽지 않는다 → 가장자리 색이 이어진다
    px = np.clip(px, sx0 + 2, sx1 - 2)
    py = np.clip(py, 0, photo.shape[0] - 1)
    scores = []
    for i in range(len(names)):
        onehot = nd.gaussian_filter((labels == i).astype(np.float32), 1.5)
        scores.append(nd.map_coordinates(onehot, [py, px], order=1))
    best = np.argmax(np.stack(scores), axis=0)
    cols = np.array([_rgb(c) for c in palette.values()], dtype=np.uint8)
    out = np.dstack([cols[best], np.full(best.shape, 255, np.uint8)])

    # 얹을 것: 사진 상자 안에서 특정 색에 가까운 픽셀만 따서 같은 좌표로
    for ov in cfg.get("overlays", []):
        x0, y0, x1, y1 = ov["box"]
        sel = np.array(_rgb(ov["select"]), dtype=np.float32)
        dist = np.sqrt(((photo.astype(np.float32) - sel) ** 2).sum(-1))
        tol = float(ov.get("tol", 90))
        if ov.get("mode") == "photo":  # select = 바탕색, 바탕과 다른 픽셀을 원래 색 그대로
            alpha = np.clip((dist - tol) / (tol * 0.5), 0, 1)
        else:  # select 색에 가까운 픽셀만 color(기본 select)로
            alpha = np.clip((tol - dist) / (tol * 0.5), 0, 1)
        m = np.zeros_like(alpha)
        m[y0:y1, x0:x1] = alpha[y0:y1, x0:x1]
        m = nd.gaussian_filter(m, 0.5)
        du, dv = ov.get("offset_uv", [0, 0])
        qx, qy = panel.to_photo(uu - du, vv - dv)
        sc = float(ov.get("scale", 1.0))  # 상자 가운데 기준 확대·축소
        if sc != 1.0:
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            qx, qy = cx + (qx - cx) / sc, cy + (qy - cy) / sc
        a = nd.map_coordinates(m, [qy, qx], order=1)
        a = np.clip((a - 0.5) * 4 + 0.5, 0, 1)[..., None]  # 경계를 다시 또렷하게
        if ov.get("mode") == "photo":
            color = np.dstack(
                [
                    nd.map_coordinates(photo[..., c].astype(np.float32), [qy, qx], order=1)
                    for c in range(3)
                ]
            )
        else:
            color = np.array(_rgb(ov.get("color", ov["select"])), dtype=np.float32)
        out[..., :3] = (out[..., :3] * (1 - a) + color * a).astype(np.uint8)
    img = _pil().fromarray(out, "RGBA")
    for logo in cfg.get("logos", []):
        du, dv = logo.get("offset_uv", [0, 0])
        u0, v0, u1, v1 = panel.box_to_uv(logo["box"])
        _paste_logo(img, Path(logo["path"]), (u0 + du, v0 + dv, u1 + du, v1 + dv))
    return img


def _paste_logo(img, path: Path, box):
    Image = _pil()
    if not path.is_file():
        raise AssetError(f"로고 파일이 없습니다: {path}")
    logo = Image.open(path).convert("RGBA")
    bb = logo.getbbox()
    logo = logo.crop(bb) if bb else logo
    u0, v0, u1, v1 = (round(c) for c in box)
    s = min((u1 - u0) / logo.width, (v1 - v0) / logo.height)
    logo = logo.resize(
        (max(1, round(logo.width * s)), max(1, round(logo.height * s))), Image.LANCZOS
    )
    img.alpha_composite(logo, (u0 + (u1 - u0 - logo.width) // 2, v0 + (v1 - v0 - logo.height) // 2))


def _side(canvas, x_range, cfg: dict[str, Any], waist: int = JERSEY_BOTTOM):
    from PIL import ImageDraw, ImageFont

    Image = _pil()
    x0, x1 = x_range
    d = ImageDraw.Draw(canvas)
    d.rectangle((x0, 0, x1 - 1, waist - 1), fill=(*_rgb(cfg["bg"]), 255))
    for sx, sw, sc in cfg.get("stripes", []):  # [옆판 왼쪽에서 거리, 폭, 색]
        d.rectangle((x0 + sx, 0, x0 + sx + sw - 1, waist - 1), fill=(*_rgb(sc), 255))
    text = cfg.get("text")
    if not text:
        return
    w = x1 - x0
    top, bottom = cfg.get("text_v", [1250, 2350])
    font = ImageFont.truetype(cfg.get("font", "C:/Windows/Fonts/impact.ttf"), int(w * 0.62))
    x0b, t, r, b = font.getbbox(text)
    t_img = Image.new("RGBA", (r - x0b, b - t), (0, 0, 0, 0))
    ImageDraw.Draw(t_img).text((-x0b, -t), text, font=font, fill=(*_rgb(cfg["color"]), 255))
    length = bottom - top
    if t_img.width > length:
        t_img = t_img.resize((length, max(1, round(t_img.height * length / t_img.width))))
    t_img = t_img.rotate(-90, expand=True)  # 위→아래로 읽힘(사진과 같은 방향)
    canvas.alpha_composite(t_img, (x0 + (w - t_img.width) // 2, top))


def make_uniform(design: dict[str, Any], dst: Path, root: Path = Path(".")) -> dict:
    np, _ = _np()
    Image = _pil()
    palette = design["palette"]
    canvas = Image.new("RGBA", (S, S), (*_rgb(design["shorts"]["bg"]), 255))

    def load(name):
        p = root / design["photos"][name]
        if not p.is_file():
            raise AssetError(f"참고 사진이 없습니다: {p}")
        return np.asarray(Image.open(p).convert("RGB"))

    front = _render_panel(load("front"), design["front"], palette, FRONT[1] - FRONT[0])
    canvas.alpha_composite(front, (FRONT[0], 0))
    back = _render_panel(
        load("back"), design["back"], palette, BACK_RENDER, BACK_CENTER + (4096 - BACK_START)
    )
    left_part = 4096 - BACK_START  # 뒤에서 볼 때 왼쪽 부분은 x BACK_START~4096
    canvas.alpha_composite(back.crop((0, 0, left_part, JERSEY_BOTTOM)), (BACK_START, 0))
    canvas.alpha_composite(back.crop((left_part, 0, BACK_RENDER, JERSEY_BOTTOM)), (0, 0))
    from PIL import ImageDraw

    # 허리선(게임 확인 y≈1780) 아래는 반바지에 투영된다 → 반바지 색으로 덮는다
    waist = design.get("waist_uv", JERSEY_BOTTOM)
    if waist < JERSEY_BOTTOM:
        ImageDraw.Draw(canvas).rectangle(
            (0, waist, S - 1, JERSEY_BOTTOM - 1), fill=(*_rgb(design["shorts"]["bg"]), 255)
        )
    _side(canvas, SIDE_R, design["side_r"], waist)
    _side(canvas, SIDE_L, design["side_l"], waist)

    from PIL import ImageDraw

    d = ImageDraw.Draw(canvas)
    d.rectangle((0, BELT[0], S - 1, BELT[1] - 1), fill=(*_rgb(design["belt"]), 255))
    sh = design["shorts"]
    if sh.get("hem"):
        d.rectangle((0, SHORTS[1], S - 1, S - 1), fill=(*_rgb(sh["hem"]), 255))
    for logo in sh.get("logos", []):
        _paste_logo(canvas, root / logo["path"], logo["box_uv"])

    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(dst, "PNG")
    canvas.resize((1024, 1024)).save(dst.with_name(dst.stem + "_preview.png"))
    return {"dst": str(dst), "size": canvas.size}
