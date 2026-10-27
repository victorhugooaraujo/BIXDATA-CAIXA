import numpy as np
from PIL import Image

from caixa_inteligente.demo.runtime import DemoRecognizer


def test_no_localized_item_never_sends_shelf_to_classifier(tmp_path):
    class Detector:
        def detect(self, image):
            return None

    class ForbiddenEncoder:
        def encode(self, path):
            raise AssertionError("No product located; must not classify background")

    path = tmp_path / "scene.jpg"
    Image.new("RGB", (100, 100)).save(path)
    recognizer = DemoRecognizer(None, ForbiddenEncoder(), Detector(), [])
    result = recognizer(path)
    assert result["sku"] is None
    assert result["candidates"] == []
    assert result["reason"] == "reposition"


def test_encoder_sees_foreground_and_ocr_failure_is_visible(tmp_path):
    class Detector:
        def detect(self, image):
            return {"box": [0.25, 0.25, 0.75, 0.75], "score": 0.8}

    class Encoder:
        def encode(self, path):
            with Image.open(path) as crop:
                assert crop.size == (56, 56)
                assert crop.getpixel((28, 28))[0] > 200
            return np.array([1.0, 0])

    class Head:
        def rank(self, vector):
            return [{"sku": "a", "score": 0.7, "similarity": 0.9}]

    class Ocr:
        def read(self, path):
            raise RuntimeError("unavailable")

    path = tmp_path / "scene.png"
    image = Image.new("RGB", (100, 100), "black")
    image.paste("white", (25, 25, 75, 75))
    image.save(path)
    result = DemoRecognizer(Head(), Encoder(), Detector(), [{"sku": "a", "name": "A"}], Ocr())(path)
    assert result["sku"] == "a"
    assert result["candidates"][0]["name"] == "A"
    assert result["ocr_status"] == "unavailable"
    assert result["automatic_acceptance"] is False
