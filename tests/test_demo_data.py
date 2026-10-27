from pathlib import Path

import pytest

from caixa_inteligente.demo.dataset import (
    assign_splits,
    crop_box,
    prepare_archive,
    safe_image_members,
    validate_disjoint,
)


def test_archive_preparation_preserves_split_and_uses_reviewed_roi(tmp_path):
    import hashlib
    import zipfile
    from io import BytesIO

    from PIL import Image

    stream = BytesIO()
    image = Image.new("RGB", (100, 100), "black")
    image.paste("white", (25, 25, 75, 75))
    image.save(stream, "PNG")
    raw = stream.getvalue()
    archive = tmp_path / "photos.zip"
    with zipfile.ZipFile(archive, "w") as zipped:
        zipped.writestr("photos/IMG_1.png", raw)
    annotations = {
        "source_zip_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        "samples": [
            {
                "id": "001_IMG_1",
                "box": [0.25, 0.25, 0.75, 0.75],
                "split": "test",
                "source_sha256": hashlib.sha256(raw).hexdigest(),
                "sku": "one",
            }
        ],
    }
    output = tmp_path / "prepared"
    prepare_archive(archive, annotations, output)
    with Image.open(output / "001_IMG_1-crop.jpg") as crop:
        assert crop.size == (56, 56)
        assert crop.getpixel((28, 28))[0] > 200
    assert (output / "scenes/001_IMG_1.jpg").is_file()
    annotations["source_zip_sha256"] = "different"
    with pytest.raises(ValueError, match="ZIP"):
        prepare_archive(archive, annotations, output)


def test_evaluation_cannot_reuse_training_content_under_another_filename():
    samples = [
        {"id": "reference", "split": "train", "sha256": "same"},
        {"id": "renamed-test", "split": "test", "sha256": "same"},
    ]
    with pytest.raises(ValueError, match="split"):
        validate_disjoint(samples)
    samples[1]["sha256"] = "different"
    validate_disjoint(samples)


def test_split_is_deterministic_and_holds_back_each_real_product():
    samples = [
        {"id": f"{sku}-{i}", "sku": sku, "sha256": f"{sku}{i}"}
        for sku in ("a", "b")
        for i in range(7)
    ]
    one = assign_splits(samples, seed=17)
    two = assign_splits(list(reversed(samples)), seed=17)
    assert {s["id"]: s["split"] for s in one} == {s["id"]: s["split"] for s in two}
    for sku in ("a", "b"):
        assert {s["split"] for s in one if s["sku"] == sku} == {"train", "val", "test"}
    assert len({s["sha256"] for s in one}) == len(one)


def test_identical_image_cannot_cross_product_labels_or_splits():
    samples = [
        {"id": "one", "sku": "a", "sha256": "same"},
        {"id": "two", "sku": "b", "sha256": "same"},
    ]
    with pytest.raises(ValueError, match="duplicad"):
        assign_splits(samples)


def test_tiny_classes_do_not_silently_become_fake_test_sets():
    with pytest.raises(ValueError, match="quatro"):
        assign_splits([{"id": str(i), "sku": "a", "sha256": str(i)} for i in range(3)])


def test_crop_uses_image_coordinates_and_clamps_context():
    from PIL import Image

    image = Image.new("RGB", (100, 200), "black")
    image.paste("white", (20, 50, 80, 150))
    assert crop_box(image, [20, 50, 80, 150], context=0).size == (60, 100)
    assert crop_box(image, [0, 0, 100, 200], context=0.2).size == image.size
    for box in ([80, 50, 20, 150], [0, 0, float("nan"), 1], [1, 2, 3]):
        with pytest.raises(ValueError):
            crop_box(image, box)


def test_zip_path_traversal_and_non_images_never_reach_extraction():
    import zipfile
    from io import BytesIO

    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("photos/one.jpg", b"image")
        archive.writestr("photos/instructions.py", b"do not execute")
    with zipfile.ZipFile(buffer) as archive:
        assert [Path(m.filename).name for m in safe_image_members(archive)] == ["one.jpg"]
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("../escape.jpg", b"image")
    with zipfile.ZipFile(buffer) as archive:
        with pytest.raises(ValueError, match="caminho"):
            safe_image_members(archive)
