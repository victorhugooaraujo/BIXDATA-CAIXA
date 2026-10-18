"""Read pinned RPC Parquet exports without thousands of API requests."""

from __future__ import annotations

import hashlib
import io
import json
import math
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path, PurePosixPath
from urllib.request import urlopen

import pyarrow.parquet as parquet
from PIL import Image

REPOSITORY = "benjamintli/retail-product-checkout"
REVISION = "c86266a8f08920fea0341994863fe747ac783bc6"
HUB = f"https://huggingface.co/datasets/{REPOSITORY}/resolve/{REVISION}/"


def _sha256(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def _download_parquet(cache: Path, entry: dict, progress=None) -> Path:
    filename = PurePosixPath(entry["path"]).name
    if not filename.endswith(".parquet") or not entry["path"].startswith("data/"):
        raise ValueError("Caminho Parquet inesperado.")
    target = cache / "hf-parquet" / REVISION / filename
    target.parent.mkdir(parents=True, exist_ok=True)
    expected = entry["lfs"]["oid"]
    if target.is_file():
        if target.stat().st_size != entry["size"] or _sha256(target) != expected:
            raise ValueError(f"Cache Parquet corrompido: {target}")
        return target
    if progress:
        progress(f"RPC: baixando {filename} ({entry['size'] / 1_000_000:.0f} MB)")
    temporary = target.with_suffix(".parquet.part")
    digest, downloaded = hashlib.sha256(), 0
    with urlopen(HUB + entry["path"] + "?download=true", timeout=90) as response:
        with temporary.open("wb") as handle:
            while chunk := response.read(1024 * 1024):
                downloaded += len(chunk)
                if downloaded > entry["size"]:
                    raise ValueError("O Parquet excedeu o tamanho publicado.")
                digest.update(chunk)
                handle.write(chunk)
    if downloaded != entry["size"] or digest.hexdigest() != expected:
        raise ValueError(f"Tamanho/checksum do Parquet não confere: {filename}")
    temporary.replace(target)
    if progress:
        progress(f"RPC: checksum conferido para {filename}")
    return target


def validate_objects(objects: dict, annotations: list[dict]) -> None:
    expected = sorted(annotations, key=lambda a: (a["category_id"], a["bbox"]))
    actual = sorted(zip(objects["category"], objects["bbox"], strict=True))
    if len(expected) != len(actual) or any(
        a["category_id"] != label + 1
        or any(not math.isclose(x, y, abs_tol=0.02) for x, y in zip(a["bbox"], bbox, strict=True))
        for a, (label, bbox) in zip(expected, actual, strict=True)
    ):
        raise ValueError("Classes/caixas do espelho RPC diferem das anotações oficiais.")


def prepare_sources(
    documents: dict, cache: Path, train_limit: int, eval_limit: int, progress=None, seed: int = 42
) -> tuple[dict, dict, dict]:
    from caixa_inteligente.rpc_dataset import _download_url, _select_samples

    tree_path = cache / "hf-parquet" / REVISION / "tree.json"
    if tree_path.is_file():
        entries = json.loads(tree_path.read_bytes())
    else:
        url = f"https://huggingface.co/api/datasets/{REPOSITORY}/tree/{REVISION}/data"
        payload = _download_url(url, "mirror-tree", 2_000_000)
        entries = json.loads(payload)
        tree_path.parent.mkdir(parents=True, exist_ok=True)
        tree_path.write_bytes(payload)
    filtered, shards = {}, []
    for split, document in documents.items():
        mirror_split = "validation" if split == "val" else split
        candidates = sorted(
            [e for e in entries if e["path"].startswith(f"data/{mirror_split}-")],
            key=lambda e: e["path"],
        )
        if not candidates:
            raise ValueError(f"O espelho não contém o split {split}.")
        ordered = sorted(document["images"], key=lambda image: image["file_name"])
        by_name = {image["file_name"]: image for image in ordered}
        annotations = defaultdict(list)
        for annotation in document["annotations"]:
            annotations[annotation["image_id"]].append(annotation)

        def image_for(row, index, ordered=ordered, by_name=by_name, annotations=annotations):
            raw = row["image"]["path"]
            name = (
                PurePosixPath(raw.replace(chr(92), "/")).name
                if raw
                else ordered[index]["file_name"]
            )
            if name not in by_name:
                raise ValueError(f"Nome de imagem inesperado no espelho: {name}")
            image = by_name[name]
            validate_objects(row["objects"], annotations[image["id"]])
            return image

        paths = []
        if split == "train":
            with ThreadPoolExecutor(max_workers=3) as executor:
                paths = list(
                    executor.map(
                        lambda entry: _download_parquet(cache, entry, progress), candidates
                    )
                )
            filtered[split] = document
        else:
            available, offset = {}, 0
            for entry in candidates:
                path = _download_parquet(cache, entry, progress)
                paths.append(path)
                for batch in parquet.ParquetFile(path).iter_batches(
                    batch_size=128, columns=["image.path", "objects"]
                ):
                    for row in batch.to_pylist():
                        image = image_for(row, offset)
                        available[image["id"]] = image
                        offset += 1
                filtered[split] = {
                    **document,
                    "images": list(available.values()),
                    "annotations": [
                        a for a in document["annotations"] if a["image_id"] in available
                    ],
                }
                counts = defaultdict(set)
                for annotation in filtered[split]["annotations"]:
                    counts[annotation["category_id"]].add(annotation["image_id"])
                if (
                    len(counts) == len(document["categories"])
                    and min(map(len, counts.values())) >= eval_limit
                ):
                    break
        selected = _select_samples(
            filtered[split], split, train_limit if split == "train" else eval_limit, seed
        )
        wanted = {sample["image"]["file_name"] for sample in selected}
        cached, offset = set(), 0
        for path in paths:
            entry = next(e for e in candidates if PurePosixPath(e["path"]).name == path.name)
            shards.append(
                {"path": entry["path"], "sha256": entry["lfs"]["oid"], "bytes": entry["size"]}
            )
            for batch in parquet.ParquetFile(path).iter_batches(batch_size=16):
                for row in batch.to_pylist():
                    raw = row["image"]["path"]
                    name = (
                        PurePosixPath(raw.replace(chr(92), "/")).name
                        if raw
                        else ordered[offset]["file_name"]
                    )
                    index = offset
                    offset += 1
                    if name not in wanted:
                        continue
                    image = image_for(row, index)
                    payload = row["image"]["bytes"]
                    with Image.open(io.BytesIO(payload)) as decoded:
                        if decoded.size != (image["width"], image["height"]):
                            raise ValueError("A resolução do espelho difere das anotações.")
                    target = cache / f"{split}2019" / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    if not target.exists():
                        target.write_bytes(payload)
                        target.with_suffix(".jpg.source.json").write_text(
                            json.dumps(
                                {
                                    "provider": "huggingface-parquet",
                                    "repository": REPOSITORY,
                                    "revision": REVISION,
                                    "parquet": path.name,
                                }
                            ),
                            encoding="utf-8",
                        )
                    cached.add(name)
            if progress:
                progress(f"RPC: {len(cached)}/{len(wanted)} fontes de {split} conferidas")
        if cached != wanted:
            raise ValueError(f"O espelho não forneceu todas as imagens: {split}.")
    return (
        filtered,
        {},
        {
            "repository": REPOSITORY,
            "revision": REVISION,
            "shards": shards,
            "pool_sizes": {split: len(doc["images"]) for split, doc in filtered.items()},
            "labels_checked_against_official_annotations": True,
            "cache_policy": "reuse official v5 cache; fetch missing images from pinned Parquet",
        },
    )
