"""선수 얼굴 텍스처·초상화 생성 (ADR-0020).

얼굴: 기존 2K 얼굴 color 텍스처(정면 얼굴이 가운데 펼쳐진 배치)와 선수 정면 사진에서
얼굴 랜드마크(mediapipe FaceMesh 478점)를 찾아, 사진을 텍스처 배치로 구간별 아핀 변형한다.
  - 얼굴 윤곽 안쪽은 사진, 바깥(두피·귀·목)은 원래 텍스처를 사진 피부색으로 보정해 쓴다.
  - 경계는 거리 기반으로 부드럽게 섞는다.
초상화: 투명 배경 사진을 512² 캔버스에 2K 초상화와 같은 구도(얼굴 가운데 아래쪽)로 배치한다.

사진·결과 이미지는 저장소에 넣지 않는다(assets_private/).
"""

from __future__ import annotations

from pathlib import Path

from .assets import AssetError, _pil

# FaceMesh 얼굴 윤곽(이마~턱) 인덱스
FACE_OVAL = [
    10, 338, 297, 332, 284, 251, 389, 356, 454, 323, 361, 288, 397, 365, 379, 378, 400, 377,
    152, 148, 176, 149, 150, 136, 172, 58, 132, 93, 234, 127, 162, 21, 54, 103, 67, 109,
]  # fmt: skip
CHEEKS = [50, 280, 205, 425, 118, 347]  # 피부색 표본


def _deps():
    try:
        import mediapipe as mp
        import numpy as np
        from scipy import ndimage
        from skimage.transform import PiecewiseAffineTransform, warp
    except ImportError as e:  # pragma: no cover
        raise AssetError("mediapipe(0.10)·scikit-image·scipy 가 필요합니다") from e
    return mp, np, ndimage, PiecewiseAffineTransform, warp


def landmarks(rgb):
    """RGB 배열 → (478, 2) 픽셀 좌표. 얼굴을 못 찾으면 AssetError."""
    mp, np, *_ = _deps()
    with mp.solutions.face_mesh.FaceMesh(
        static_image_mode=True, max_num_faces=1, refine_landmarks=True
    ) as fm:
        r = fm.process(rgb)
    if not r.multi_face_landmarks:
        raise AssetError("얼굴을 찾지 못했습니다")
    h, w = rgb.shape[:2]
    return np.array([[p.x * w, p.y * h] for p in r.multi_face_landmarks[0].landmark])


def _skin(rgb, pts, np):
    vals = []
    for i in CHEEKS:
        x, y = (int(round(c)) for c in pts[i])
        patch = rgb[max(0, y - 4) : y + 5, max(0, x - 4) : x + 5].reshape(-1, 3)
        vals.append(patch)
    return np.median(np.concatenate(vals), axis=0).astype(np.float32)


def make_face_texture(donor: Path, photo: Path, dst: Path, feather: float = 0.06) -> dict:
    mp, np, nd, PiecewiseAffineTransform, warp = _deps()
    Image = _pil()
    tex = np.asarray(Image.open(donor).convert("RGB")).astype(np.float32)
    ph_img = Image.open(photo)
    ph_rgba = np.asarray(ph_img.convert("RGBA"))
    ph = ph_rgba[..., :3].copy()
    ph[ph_rgba[..., 3] < 10] = 0
    t_pts = landmarks(tex.astype(np.uint8))
    p_pts = landmarks(ph)

    # 바깥 영역(두피·귀·목): 원래 텍스처 피부색 → 사진 피부색 (채널별 비율)
    tex_skin = _skin(tex, t_pts, np)
    gain = _skin(ph.astype(np.float32), p_pts, np) / np.maximum(tex_skin, 1)
    base = tex.copy()
    # 원래 선수의 수염 지우기: 입 아래쪽에서 피부보다 확연히 어두운 털은 주변 피부로 메운다
    lum = base.mean(-1)
    below_mouth = np.zeros(lum.shape, bool)
    jaw_x0, jaw_x1 = sorted((t_pts[172][0], t_pts[397][0]))  # 턱 양끝 안쪽만
    below_mouth[int(t_pts[14][1]) :, int(jaw_x0) : int(jaw_x1)] = True
    beard = below_mouth & (lum < tex_skin.mean() * 0.62)
    beard = nd.binary_dilation(beard, iterations=4)
    if beard.any():
        idx = nd.distance_transform_edt(beard, return_distances=False, return_indices=True)
        base = base[tuple(idx)]
        base = np.where(beard[..., None], nd.gaussian_filter(base, (6, 6, 0)), base)
    # 피부색 보정은 피부에만. 두피에 그려진 어두운 머리카락은 밝히지 않고 검은 머리로
    skin_l = float(tex_skin.mean())
    lum = base.mean(-1, keepdims=True)
    t = np.clip((lum - 0.45 * skin_l) / (0.35 * skin_l), 0, 1)
    scalp_bottom = int(min(t_pts[i][1] for i in (105, 66, 334, 296)))  # 눈썹 위만 두피로 본다
    ramp = np.clip((np.arange(t.shape[0]) - scalp_bottom + 40) / 80.0, 0, 1)[:, None, None]
    t = np.maximum(t, ramp)
    hair = np.clip(lum / max(skin_l, 1) * np.array([42, 38, 36], np.float32), 0, 60)
    base = np.clip(base * gain * t + hair * (1 - t), 0, 255)

    # 얼굴 안쪽: 텍스처 좌표 → 사진 좌표 구간별 아핀
    tform = PiecewiseAffineTransform.from_estimate(t_pts, p_pts)
    if not tform:
        raise AssetError("변형 추정 실패")
    warped = warp(ph.astype(np.float32) / 255.0, tform, output_shape=tex.shape[:2], order=1) * 255

    from PIL import ImageDraw

    mask_img = Image.new("L", (tex.shape[1], tex.shape[0]), 0)
    # 사진은 눈썹 조금 위까지만 쓴다(사진 이마의 앞머리가 들어오지 않게) — 이마는 원래 텍스처
    brow_y = min(t_pts[i][1] for i in (105, 66, 334, 296))
    eye_gap = abs(t_pts[263][0] - t_pts[33][0])
    top = brow_y - 0.04 * eye_gap
    poly = [(x, max(y, top)) for x, y in (t_pts[i] for i in FACE_OVAL)]
    ImageDraw.Draw(mask_img).polygon(poly, fill=255)
    inside = np.asarray(mask_img) > 0
    dist = nd.distance_transform_edt(inside)
    soft = np.clip(dist / (feather * tex.shape[0]), 0, 1)[..., None]
    out = base * (1 - soft) + warped * soft
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(out.astype(np.uint8), "RGB").save(dst)
    return {"dst": str(dst), "gain": [round(float(g), 3) for g in gain]}


def make_portrait(photo: Path, dst: Path, size: int = 512) -> dict:
    """2K 초상화 구도: 얼굴 중심 x 0.5, 눈 높이 ≈ 0.58, 얼굴 폭 ≈ 0.4 (chr_g 원본 기준)."""
    _mp, np, *_ = _deps()
    Image = _pil()
    im = Image.open(photo).convert("RGBA")
    a = np.asarray(im)
    pts = landmarks(np.ascontiguousarray(a[..., :3]))
    left, right = pts[234], pts[454]  # 광대 양끝
    eyes_y = (pts[33][1] + pts[263][1]) / 2
    cx = (left[0] + right[0]) / 2
    face_w = np.linalg.norm(right - left)
    s = size * 0.40 / face_w
    im2 = im.resize((round(im.width * s), round(im.height * s)), Image.LANCZOS)
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas.alpha_composite(im2, (round(size * 0.5 - cx * s), round(size * 0.58 - eyes_y * s)))
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(dst)
    return {"dst": str(dst), "size": size}
