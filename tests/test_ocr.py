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


def test_concurrent_readers_of_same_image_publish_one_complete_cache(tmp_path, monkeypatch):
    import threading
    from concurrent.futures import ThreadPoolExecutor
    from pathlib import Path

    class Engine:
        def __init__(self, params):
            pass

        def __call__(self, pixels):
            return types.SimpleNamespace(txts=None)

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
    barrier = threading.Barrier(2)
    original_write = Path.write_text

    def synchronized_write(path, *args, **kwargs):
        result = original_write(path, *args, **kwargs)
        if path.suffix == ".tmp":
            barrier.wait(timeout=5)
        return result

    monkeypatch.setattr(Path, "write_text", synchronized_write)
    cache = tmp_path / "cache"
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: OcrReader(cache).read(image), range(2)))
    assert results[0] == results[1]
    assert len(list(cache.glob("*.json"))) == 1
    assert not list(cache.glob("*.tmp"))
