import copy
import hashlib
import json

import pyarrow as arrow
import pyarrow.parquet as parquet
import pytest
from test_rpc_dataset import fixture_sources

from caixa_inteligente import rpc_mirror as mirror


def objects_for(document, image):
    annotations = [a for a in document["annotations"] if a["image_id"] == image["id"]]
    return {
        "category": [a["category_id"] - 1 for a in annotations],
        "bbox": [a["bbox"] for a in annotations],
    }, annotations


def test_mirror_labels_and_boxes_match_official_metadata():
    document = json.loads(fixture_sources()["instances_train2019.json"])
    objects, annotations = objects_for(document, document["images"][0])
    mirror.validate_objects(objects, annotations)
    objects = copy.deepcopy(objects)
    objects["bbox"][0][0] += 0.001
    mirror.validate_objects(objects, annotations)


@pytest.mark.parametrize("change", ["label", "bbox", "count"])
def test_mirror_mismatch_fails_instead_of_assigning_wrong_products(change):
    document = json.loads(fixture_sources()["instances_train2019.json"])
    objects, annotations = objects_for(document, document["images"][0])
    objects = copy.deepcopy(objects)
    if change == "label":
        objects["category"][0] += 1
    elif change == "bbox":
        objects["bbox"][0][0] += 10
    else:
        objects["category"] = []
        objects["bbox"] = []
    with pytest.raises(ValueError):
        mirror.validate_objects(objects, annotations)


def test_parquet_cache_requires_published_hash(tmp_path):
    cache = tmp_path / "hf-parquet" / mirror.REVISION
    cache.mkdir(parents=True)
    path = cache / "train-0.parquet"
    path.write_bytes(b"corrupt")
    entry = {"path": "data/train-0.parquet", "size": 7, "lfs": {"oid": "0" * 64}}
    with pytest.raises(ValueError, match="corrompido"):
        mirror._download_parquet(tmp_path, entry)


def test_prepare_sources_extracts_only_selected_rows_from_verified_parquet(tmp_path, monkeypatch):
    sources = fixture_sources()
    documents = {
        split: json.loads(sources[f"instances_{split}2019.json"])
        for split in ("train", "val", "test")
    }
    shard_dir = tmp_path / "hf-parquet" / mirror.REVISION
    shard_dir.mkdir(parents=True)
    entries = []
    for split, document in documents.items():
        rows = []
        for image in sorted(document["images"], key=lambda item: item["file_name"]):
            objects, _ = objects_for(document, image)
            rows.append(
                {
                    "image": {
                        "path": image["file_name"],
                        "bytes": sources[f"{split}2019/{image['file_name']}"],
                    },
                    "objects": objects,
                }
            )
        mirror_split = "validation" if split == "val" else split
        path = shard_dir / f"{mirror_split}-0.parquet"
        parquet.write_table(arrow.Table.from_pylist(rows), path)
        entries.append(
            {
                "path": "data/" + path.name,
                "size": path.stat().st_size,
                "lfs": {"oid": hashlib.sha256(path.read_bytes()).hexdigest()},
            }
        )
    (shard_dir / "tree.json").write_text(json.dumps(entries), encoding="utf-8")
    prepared, urls, info = mirror.prepare_sources(documents, tmp_path, 2, 1)
    assert not urls
    assert info["revision"] == mirror.REVISION
    assert info["labels_checked_against_official_annotations"] is True
    assert len(info["shards"]) == 3
    assert len(prepared["train"]["images"]) == 6
    assert len(list((tmp_path / "train2019").glob("*.jpg"))) == 4
    assert len(list((tmp_path / "val2019").glob("*.jpg"))) == 2
    assert len(list((tmp_path / "test2019").glob("*.jpg"))) == 2
