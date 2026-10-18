import io
import json
import zipfile
from collections import Counter

import pytest
from PIL import Image

from caixa_inteligente import rpc_dataset as rpc


def fixture_sources():
    sources = {}
    for split_number, split in enumerate(rpc.SPLITS):
        document = {
            "categories": [
                {"id": 1, "name": "1_puffed_food", "supercategory": "puffed_food"},
                {"id": 164, "name": "164_personal_hygiene", "supercategory": "personal_hygiene"},
            ],
            "images": [],
            "annotations": [],
        }
        for category in document["categories"]:
            for index in range(3):
                image_id = category["id"] * 10 + index
                name = f"{split}-{image_id}.jpg"
                document["images"].append(
                    {
                        "id": image_id,
                        "file_name": name,
                        "width": 60,
                        "height": 40,
                        "level": "easy",
                    }
                )
                document["annotations"].append(
                    {
                        "id": image_id,
                        "image_id": image_id,
                        "category_id": category["id"],
                        "bbox": [10, 5, 25, 30],
                        "iscrowd": 0,
                    }
                )
                buffer = io.BytesIO()
                color = (split_number * 80, category["id"], index * 60)
                Image.new("RGB", (60, 40), color).save(buffer, format="PNG")
                sources[f"{split}2019/{name}"] = buffer.getvalue()
        sources[f"instances_{split}2019.json"] = json.dumps(document).encode()
    return sources


@pytest.fixture
def mocked_download(monkeypatch):
    sources = fixture_sources()
    monkeypatch.setattr(rpc, "_download_file", lambda relative, limit: sources[relative])
    return sources


def test_rpc_install_preserves_official_splits_and_distinct_namespaces(tmp_path, mocked_download):
    destination = tmp_path / "rpc"
    report = rpc.download_rpc_subset(
        destination,
        tmp_path / "cache",
        train_per_class=2,
        eval_per_class=1,
        workers=2,
        source="kaggle",
    )
    assert report["counts"] == {"train": 4, "val": 2, "test": 2}
    assert report["classes"] == 2
    assert report["total_images"] == 8
    manifest = json.loads((destination / "source_manifest.json").read_text(encoding="utf-8"))
    assert manifest["classification_uses_ground_truth_boxes"] is True
    assert manifest["dataset_version"] == 5
    assert set(sample["sku"] for sample in manifest["images"]) == {"rpc-001", "rpc-164"}
    for sample in manifest["images"]:
        assert sample["source_file"].startswith(sample["split"] + "2019/")
        with Image.open(destination / sample["local_path"]) as crop:
            assert crop.mode == "RGB"
            assert max(crop.size) <= 512
    catalog = (destination / "catalog.csv").read_text(encoding="utf-8")
    assert "rpc-001,Salgadinhos / RPC 001,1.00" in catalog
    assert "rpc-164,Higiene pessoal / RPC 164,1.00" in catalog
    assert (destination / "LICENSE-RPC.txt").is_file()


def test_selection_is_deterministic_and_does_not_repeat_an_image(mocked_download):
    document = json.loads(mocked_download["instances_train2019.json"])
    first = rpc._select_samples(document, "train", 2, 42)
    assert first == rpc._select_samples(document, "train", 2, 42)
    assert Counter(s["annotation"]["category_id"] for s in first) == {1: 2, 164: 2}
    assert len({s["image"]["id"] for s in first}) == 4


@pytest.mark.parametrize("name", ["../escape.jpg", "C:/escape.jpg", "a\\b.jpg", "a/b.jpg", ""])
def test_rejects_untrusted_image_paths(name):
    with pytest.raises(ValueError, match="arquivo RPC inválido"):
        rpc._safe_name(name)


def test_insufficient_images_is_an_error(mocked_download):
    document = json.loads(mocked_download["instances_train2019.json"])
    with pytest.raises(ValueError, match="insuficientes"):
        rpc._select_samples(document, "train", 4, 42)


def test_invalid_box_is_not_silently_cropped(mocked_download):
    document = json.loads(mocked_download["instances_train2019.json"])
    document["annotations"][0]["bbox"] = [0, 0, float("nan"), 2]
    with pytest.raises(ValueError, match="Bounding box"):
        rpc._select_samples(document, "train", 1, 42)


def test_existing_destination_is_never_overwritten(tmp_path):
    destination = tmp_path / "rpc"
    destination.mkdir()
    (destination / "my-file").write_text("keep", encoding="utf-8")
    with pytest.raises(ValueError, match="já existe"):
        rpc.download_rpc_subset(destination, tmp_path / "cache")
    assert (destination / "my-file").read_text(encoding="utf-8") == "keep"


def test_failure_leaves_no_published_partial_dataset(tmp_path, mocked_download):
    for relative in mocked_download:
        if relative.endswith(".jpg"):
            mocked_download[relative] = b"corrupt-image"
    with pytest.raises(OSError):
        rpc.download_rpc_subset(
            tmp_path / "rpc", tmp_path / "cache", 1, 1, workers=1, source="kaggle"
        )
    assert not (tmp_path / "rpc").exists()
    assert not list(tmp_path.glob(".rpc-preparing-*"))


@pytest.mark.parametrize(
    "arguments", [{"workers": 17}, {"train_per_class": True}, {"eval_per_class": 0}]
)
def test_invalid_limits_fail_before_network(tmp_path, arguments):
    with pytest.raises(ValueError):
        rpc.download_rpc_subset(tmp_path / "rpc", tmp_path / "cache", **arguments)


def test_download_encodes_path_and_unwraps_single_json_file(monkeypatch):
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as archive:
        archive.writestr("instances_train2019.json", b'{"categories":[]}')

    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *_):
            self.close()

    urls = []

    def urlopen(url, timeout):
        urls.append(url)
        return Response(payload.getvalue())

    monkeypatch.setattr(rpc, "urlopen", urlopen)
    assert rpc._download_file("instances_train2019.json", 10000) == b'{"categories":[]}'
    assert urls[0].endswith("instances_train2019.json?datasetVersionNumber=5")
    monkeypatch.setattr(rpc, "urlopen", lambda url, timeout: Response(b"jpeg-fixture"))
    assert rpc._download_file("train2019/a.jpg", 10000) == b"jpeg-fixture"


def test_archive_members_cannot_write_outside_destination(monkeypatch):
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as archive:
        archive.writestr("../escape.json", b"bad")
    monkeypatch.setattr(rpc, "urlopen", lambda url, timeout: io.BytesIO(payload.getvalue()))
    with pytest.raises(ValueError, match="ZIP RPC inesperado"):
        rpc._download_file("instances_train2019.json", 10000)


def test_rate_limit_stops_download_without_retry_storm(monkeypatch):
    from urllib.error import HTTPError

    calls = []

    def limited(url, timeout):
        calls.append(url)
        raise HTTPError(url, 429, "Too Many Requests", {}, None)

    monkeypatch.setattr(rpc, "urlopen", limited)
    with pytest.raises(RuntimeError, match="HTTP 429"):
        rpc._download_file("train2019/a.jpg", 10000)
    assert len(calls) == 1
