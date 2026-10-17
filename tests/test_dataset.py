import csv
import hashlib
import io
import json
from urllib.error import URLError

import pytest

from caixa_inteligente import dataset


@pytest.fixture
def upstream(monkeypatch):
    """Mirror the official metadata format without internet or real images."""
    files = {
        "LICENSE": b"MIT License\nCopyright (c) 2019 Marcus Klasson\n",
        "dataset/classes.csv": (
            b"Class Name (str),Class ID (int),Coarse Class Name (str),"
            b"Coarse Class ID (int),Iconic Image Path (str),Product Description Path (str)\n"
            b"Banana,6,Banana,2,/iconic/banana.jpg,/description/banana.txt\n"
            b"Orange,16,Orange,9,/iconic/orange.jpg,/description/orange.txt\n"
            b"Cucumber,63,Cucumber,32,/iconic/cucumber.jpg,/description/cucumber.txt\n"
        ),
    }
    for split in dataset.SPLITS:
        rows = []
        for name, class_id, coarse_id in (
            ("Banana", 6, 2),
            ("Orange", 16, 9),
            ("Cucumber", 63, 32),
        ):
            for index in range(3):
                path = f"{split}/Fruit/{name}/{name}_{index:03d}.jpg"
                rows.append(f"{path}, {class_id}, {coarse_id}\n")
                files["dataset/" + path] = b"\xff\xd8\xff" + path.encode() + b"\xff\xd9"
        files[f"dataset/{split}.txt"] = "".join(rows).encode()
    requests = []

    def fake_urlopen(url, timeout):
        assert timeout == 30
        assert url.startswith(dataset.GROCERY_RAW_URL)
        requests.append(url)
        return io.BytesIO(files[url.removeprefix(dataset.GROCERY_RAW_URL)])

    monkeypatch.setattr(dataset, "urlopen", fake_urlopen)
    return files, requests


def test_subset_preserves_splits_limits_provenance_and_license(tmp_path, upstream):
    files, requests = upstream
    destination = tmp_path / "grocery"
    result = dataset.download_grocery_subset(
        destination, max_train_per_class=2, max_eval_per_class=1
    )
    assert result["counts"] == {"train": 6, "val": 3, "test": 3}
    assert result["total_images"] == 12
    assert len(requests) == 17  # Five metadata files, twelve selected images.
    assert (destination / "LICENSE").read_bytes() == files["LICENSE"]
    manifest = json.loads((destination / "source_manifest.json").read_text(encoding="utf-8"))
    assert manifest["revision"] == dataset.GROCERY_REVISION
    assert manifest["prices_are_demo"] is True
    assert len(manifest["images"]) == 12
    for row in manifest["images"]:
        assert row["source_path"].startswith(row["split"] + "/")
        assert row["local_path"].startswith(f"{row['split']}/{row['class_id']}/")
        payload = (destination / row["local_path"]).read_bytes()
        assert payload == files["dataset/" + row["source_path"]]
        assert row["sha256"] == hashlib.sha256(payload).hexdigest()
    with (destination / "catalog.csv").open(encoding="utf-8", newline="") as handle:
        assert list(csv.DictReader(handle)) == [
            {"sku": "6", "name": "Banana", "price": "1.00"},
            {"sku": "16", "name": "Orange", "price": "1.00"},
            {"sku": "63", "name": "Cucumber", "price": "1.00"},
        ]


@pytest.mark.parametrize("classes", [(), (6, 6), (-1,), (True,), ("6",)])
def test_invalid_selection_is_rejected_before_network(tmp_path, upstream, classes):
    _, requests = upstream
    with pytest.raises(ValueError):
        dataset.download_grocery_subset(tmp_path / "grocery", class_ids=classes)
    assert requests == []


@pytest.mark.parametrize("limit", [0, -1, True, 1.5])
def test_invalid_limits_are_rejected(tmp_path, upstream, limit):
    with pytest.raises(ValueError, match="inteiro positivo"):
        dataset.download_grocery_subset(tmp_path / "grocery", max_train_per_class=limit)


@pytest.mark.parametrize(
    "source_path",
    [
        "train/../outside.jpg",
        "/train/Fruit/banana.jpg",
        "test/Fruit/banana.jpg",
        "train\\Fruit\\banana.jpg",
        "train/C:/banana.jpg",
        "train//banana.jpg",
    ],
)
def test_path_traversal_and_wrong_split_are_rejected(tmp_path, upstream, source_path):
    files, _ = upstream
    files["dataset/train.txt"] = f"{source_path}, 6, 2\n".encode()
    with pytest.raises(ValueError, match="Caminho inseguro"):
        dataset.download_grocery_subset(tmp_path / "grocery")
    assert not (tmp_path / "grocery").exists()
    assert not (tmp_path / "outside.jpg").exists()


def test_unknown_class_and_empty_split_are_rejected(tmp_path, upstream):
    files, _ = upstream
    with pytest.raises(ValueError, match="Classes inexistentes"):
        dataset.download_grocery_subset(tmp_path / "unknown", class_ids=(100,))
    files["dataset/val.txt"] = b"\n"
    with pytest.raises(ValueError, match="está vazio"):
        dataset.download_grocery_subset(tmp_path / "empty")


def test_class_must_exist_in_every_split(tmp_path, upstream):
    files, _ = upstream
    files["dataset/val.txt"] = b"val/Fruit/Banana/Banana_000.jpg, 6, 2\n"
    with pytest.raises(ValueError, match="Classes sem imagens no split val"):
        dataset.download_grocery_subset(tmp_path / "grocery")


def test_duplicate_images_across_splits_are_rejected(tmp_path, upstream):
    files, _ = upstream
    files["dataset/val/Fruit/Banana/Banana_000.jpg"] = files[
        "dataset/train/Fruit/Banana/Banana_000.jpg"
    ]
    with pytest.raises(ValueError, match="duplicada entre splits"):
        dataset.download_grocery_subset(tmp_path / "grocery")
    assert not (tmp_path / "grocery").exists()
    assert list(tmp_path.iterdir()) == []


def test_network_failure_does_not_leave_partial_dataset(tmp_path, upstream, monkeypatch):
    original = dataset.urlopen

    def failing_urlopen(url, timeout):
        if url.endswith("Banana_001.jpg"):
            raise URLError("fixture network unavailable")
        return original(url, timeout)

    monkeypatch.setattr(dataset, "urlopen", failing_urlopen)
    with pytest.raises(RuntimeError, match="Não foi possível baixar"):
        dataset.download_grocery_subset(tmp_path / "grocery")
    assert list(tmp_path.iterdir()) == []


def test_existing_dataset_is_never_overwritten(tmp_path, upstream):
    destination = tmp_path / "grocery"
    destination.mkdir()
    sentinel = destination / "my-images.txt"
    sentinel.write_text("keep", encoding="utf-8")
    with pytest.raises(ValueError, match="pasta vazia"):
        dataset.download_grocery_subset(destination)
    assert sentinel.read_text(encoding="utf-8") == "keep"


def test_html_response_does_not_become_an_image(tmp_path, upstream):
    files, _ = upstream
    files["dataset/train/Fruit/Banana/Banana_000.jpg"] = b"<html>error</html>"
    with pytest.raises(ValueError, match="não é uma imagem"):
        dataset.download_grocery_subset(tmp_path / "grocery")
    assert list(tmp_path.iterdir()) == []
