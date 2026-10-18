import sys
import types
from enum import Enum

import numpy as np
from PIL import Image

from caixa_inteligente.ocr import OcrReader


class Version(Enum):
    PPOCRV4 = "PP-OCRv4"


class Model(Enum):
    MOBILE = "mobile"


def test_content_cache_preserves_evidence_and_invalidates_changed_image(tmp_path, monkeypatch):
    calls = []

    class Engine:
        def __init__(self, params):
            assert params["Det.ocr_version"] is Version.PPOCRV4
            assert params["Rec.model_type"] is Model.MOBILE

        def __call__(self, pixels):
            calls.append(pixels[0, 0].tolist())
            return types.SimpleNamespace(txts=("500 g",), scores=(0.9,), boxes=np.zeros((1, 4, 2)))

    monkeypatch.setitem(
        sys.modules,
        "rapidocr",
        types.SimpleNamespace(RapidOCR=Engine, OCRVersion=Version, ModelType=Model),
    )
    monkeypatch.setattr(
        "importlib.metadata.version",
        lambda name: {"rapidocr": "3.10.0", "onnxruntime": "1.31.0"}[name],
    )
    image = tmp_path / "product.png"
    Image.new("RGB", (20, 20), "red").save(image)
    reader = OcrReader(tmp_path / "cache")
    first = reader.read(image)
    assert calls == [[0, 0, 255]]
    assert first["lines"][0]["text"] == "500 g"
    # A fresh reader uses cached evidence without importing/loading OCR again.
    assert OcrReader(tmp_path / "cache").read(image) == first
    assert len(calls) == 1
    Image.new("RGB", (20, 20), "blue").save(image)
    assert reader.read(image)["sha256"] != first["sha256"]
    assert calls[-1] == [255, 0, 0]
