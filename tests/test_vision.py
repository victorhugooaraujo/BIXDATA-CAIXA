"""Offline tests: synthetic embeddings, no model or dataset downloads."""

import json
import sys
import types
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pytest

from caixa_inteligente.vision import (
    DINOV2_REVISION,
    DINOV2_SIGNATURE,
    DinoV2Encoder,
    Gallery,
)


class FakeEncoder:
    signature = DINOV2_SIGNATURE

    def __init__(self, vectors):
        self.vectors = vectors

    def encode(self, path):
        return np.asarray(self.vectors[path.name], dtype=np.float32)


def make_gallery(references):
    encoder = FakeEncoder({str(i): vector for i, (_, vector) in enumerate(references)})
    return Gallery.build([(sku, Path(str(i))) for i, (sku, _) in enumerate(references)], encoder)


def test_margin_compares_classes_instead_of_individual_reference_images():
    gallery = make_gallery([("a", [1, 0]), ("a", [0.99, 0.01]), ("b", [0, 1])])
    result = gallery.recognize(np.array([20, 0]))
    assert result.sku == "a"
    assert result.reason == "accepted"
    assert result.similarity == pytest.approx(1.0)
    assert result.margin == pytest.approx(1.0)
    assert gallery.sample_count == 3
    assert gallery.class_count == 2
    assert [candidate.sku for candidate in result.candidates] == ["a", "b"]
    assert asdict(result)["candidates"][0] == {"sku": "a", "similarity": 1.0}


def test_rejects_low_similarity():
    gallery = make_gallery([("a", [1, 0]), ("b", [0, 1])])
    result = gallery.recognize(np.array([1, 1]))
    assert result.sku is None
    assert result.reason == "below_similarity"
    assert result.similarity == pytest.approx(2**-0.5)


def test_rejects_ambiguous_match_with_sufficient_similarity():
    gallery = make_gallery([("a", [1, 0]), ("b", [0.99, 0.01])])
    result = gallery.recognize(np.array([1, 0]))
    assert result.sku is None
    assert result.reason == "ambiguous"
    assert 0 <= result.margin < 0.05


def test_rejects_single_class_even_with_perfect_match():
    gallery = make_gallery([("a", [1, 0]), ("a", [0.99, 0.01])])
    result = gallery.recognize(np.array([1, 0]), min_margin=0)
    assert result.sku is None
    assert result.reason == "single_class"
    assert result.margin == 0


def test_returns_at_most_three_candidates_and_orders_ties_by_sku():
    gallery = make_gallery([(sku, [1, 0]) for sku in ["d", "c", "b", "a"]])
    result = gallery.recognize(np.array([1, 0]))
    assert [candidate.sku for candidate in result.candidates] == ["a", "b", "c"]
    assert result.reason == "ambiguous"


@pytest.mark.parametrize("vector", [[0, 0], [np.nan, 0], [np.inf, 0], [[1, 0]], [], [1, 2, 3]])
def test_rejects_invalid_query_vectors(vector):
    gallery = make_gallery([("a", [1, 0]), ("b", [0, 1])])
    with pytest.raises(ValueError):
        gallery.recognize(np.asarray(vector))


def test_rejects_inconsistent_reference_dimensions():
    with pytest.raises(ValueError, match="same dimension"):
        make_gallery([("a", [1, 0]), ("b", [1, 0, 0])])


def test_rejects_empty_gallery_and_invalid_sku():
    with pytest.raises(ValueError, match="At least one"):
        Gallery.build([], FakeEncoder({}))
    with pytest.raises(ValueError, match="SKUs"):
        make_gallery([(" ", [1, 0])])


@pytest.mark.parametrize(
    "kwargs", [{"min_similarity": np.nan}, {"min_similarity": 1.1}, {"min_margin": -1}]
)
def test_validates_recognition_thresholds(kwargs):
    gallery = make_gallery([("a", [1, 0]), ("b", [0, 1])])
    with pytest.raises(ValueError):
        gallery.recognize(np.array([1, 0]), **kwargs)


def test_gallery_round_trip_uses_plain_npz_arrays(tmp_path):
    gallery = make_gallery([("cafe", [1, 0]), ("leite", [0, 1])])
    path = tmp_path / "nested" / "gallery.npz"
    gallery.save(path)
    with np.load(path, allow_pickle=False) as archive:
        metadata = json.loads(archive["metadata"].item())
        assert metadata["model_identifier"].endswith(":dinov2_vits14")
        assert metadata["preprocessing_schema"].endswith("imagenet-v1")
        assert all(archive[key].dtype.kind != "O" for key in archive.files)
    restored = Gallery.load(path)
    assert restored.signature == DINOV2_SIGNATURE
    assert restored.recognize(np.array([1, 0])).sku == "cafe"


@pytest.mark.parametrize(
    "field,value", [("model", "different-model"), ("preprocessing", "different-preprocessing")]
)
def test_rejects_gallery_built_with_different_encoder_signature(tmp_path, field, value):
    details = json.loads(DINOV2_SIGNATURE)
    details[field] = value
    fake_signature = json.dumps(details, sort_keys=True, separators=(",", ":"))
    gallery = Gallery(["a", "b"], np.eye(2), fake_signature)
    path = tmp_path / "gallery.npz"
    gallery.save(path)
    with pytest.raises(ValueError, match="incompatible"):
        Gallery.load(path)
    assert Gallery.load(path, expected_signature=fake_signature).class_count == 2


def test_rejects_pickle_objects_in_archive(tmp_path):
    path = tmp_path / "gallery.npz"
    np.savez(
        path, embeddings=np.eye(2), skus=np.array(["a", "b"]), metadata=np.array({}, dtype=object)
    )
    with pytest.raises(ValueError, match="Object arrays"):
        Gallery.load(path)


def test_rejects_metadata_dimension_mismatch(tmp_path):
    path = tmp_path / "gallery.npz"
    make_gallery([("a", [1, 0]), ("b", [0, 1])]).save(path)
    with np.load(path, allow_pickle=False) as archive:
        contents = {key: archive[key] for key in archive.files}
    metadata = json.loads(contents["metadata"].item())
    metadata["embedding_dimension"] = 384
    contents["metadata"] = np.asarray(json.dumps(metadata))
    np.savez(path, **contents)
    with pytest.raises(ValueError, match="dimensions"):
        Gallery.load(path)


def test_encoder_is_lazy_and_pins_frozen_model(monkeypatch):
    calls = []

    class Model:
        def eval(self):
            calls.append("eval")

        def requires_grad_(self, value):
            calls.append(("requires_grad", value))

        def to(self, device):
            calls.append(("device", device))
            return self

    def fake_load(*args, **kwargs):
        calls.append((args, kwargs))
        return Model()

    monkeypatch.setitem(
        sys.modules, "torch", types.SimpleNamespace(hub=types.SimpleNamespace(load=fake_load))
    )
    encoder = DinoV2Encoder()
    assert encoder.signature == DINOV2_SIGNATURE
    assert calls == []
    assert encoder._load_model() is encoder._load_model()
    args, kwargs = calls[0]
    assert args == (f"facebookresearch/dinov2:{DINOV2_REVISION}", "dinov2_vits14")
    assert kwargs["pretrained"] is True
    assert ("requires_grad", False) in calls
    assert ("device", "cpu") in calls
    assert len(calls) == 4


def test_preprocess_converts_grayscale_and_normalizes_imagenet_channels(tmp_path):
    import torch
    from PIL import Image

    from caixa_inteligente.vision import _preprocess_image

    path = tmp_path / "white.png"
    Image.new("L", (60, 200), color=255).save(path)
    tensor = _preprocess_image(path)
    assert tuple(tensor.shape) == (3, 224, 224)
    assert tensor.dtype == torch.float32
    assert torch.isfinite(tensor).all()
    expected = torch.tensor([(1 - 0.485) / 0.229, (1 - 0.456) / 0.224, (1 - 0.406) / 0.225])
    assert torch.allclose(tensor[:, 100, 100], expected)


def test_preprocess_applies_exif_orientation(tmp_path):
    import torch
    from PIL import Image

    from caixa_inteligente.vision import _preprocess_image

    image = Image.new("RGB", (80, 160), color="red")
    image.paste("blue", (0, 80, 80, 160))
    exif = image.getexif()
    exif[274] = 6  # Camera orientation: rotate 90 degrees clockwise for display.
    camera_path = tmp_path / "camera.jpg"
    image.save(camera_path, exif=exif)
    expected_path = tmp_path / "upright.png"
    with Image.open(camera_path) as decoded:
        decoded.transpose(Image.Transpose.ROTATE_270).save(expected_path)
    assert torch.allclose(_preprocess_image(camera_path), _preprocess_image(expected_path))
