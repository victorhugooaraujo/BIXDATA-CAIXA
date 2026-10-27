import pytest

from caixa_inteligente.demo.detection import select_foreground


def test_price_sign_and_shelf_do_not_displace_centered_item():
    boxes = [
        {"box": [0.4, 0.1, 0.6, 0.22], "score": 0.9},
        {"box": [0.35, 0.25, 0.65, 0.8], "score": 0.45},
        {"box": [0, 0, 1, 1], "score": 0.95},
    ]
    assert select_foreground(boxes)["box"] == boxes[1]["box"]


def test_empty_scene_is_review_and_bad_coordinates_rejected():
    assert select_foreground([]) is None
    with pytest.raises(ValueError):
        select_foreground([{"box": [0.7, 0, 0.2, 1], "score": 0.8}])


def test_separate_objects_outside_presentation_zone_are_not_selected():
    assert select_foreground([{"box": [0, 0, 0.1, 0.2], "score": 0.99}]) is None
