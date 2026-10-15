"""유니폼 전개도 보조 함수 테스트 (합성 데이터)."""

import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("scipy")

from kbl2k.uniform import Panel, classify, fill_from_nearest  # noqa: E402


def test_panel_maps_seams_and_anchors():
    p = Panel({"seams": [100, 500], "anchors": [[200, 0], [700, 2500]]}, width=1600)
    assert p.box_to_uv([100, 200, 500, 700]) == (0, 0, 1600, 2500)
    x, y = p.to_photo(800, 1250)
    assert (x, y) == (300, 450)


def test_classify_and_fill():
    photo = np.zeros((4, 4, 3), np.uint8)
    photo[:, 2:] = (200, 20, 30)  # 오른쪽 빨강
    photo[1, 1] = (255, 255, 255)  # 흰 글자 한 점
    labels = classify(photo, {"black": "#000000", "red": "#C8102E", "white": "#FFFFFF"})
    assert labels[1, 1] == 2 and labels[0, 3] == 1
    filled = fill_from_nearest(labels, labels == 2)
    assert filled[1, 1] == 0  # 가장 가까운 검정으로 메워짐
