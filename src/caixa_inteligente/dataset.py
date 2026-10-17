"""Acquire a small, reproducible subset of the official Grocery Store Dataset."""

from __future__ import annotations

import csv
import hashlib
import io
import json
from collections import Counter
from decimal import Decimal
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from urllib.error import URLError
from urllib.parse import quote
from urllib.request import urlopen

GROCERY_REPOSITORY = "https://github.com/marcusklasson/GroceryStoreDataset"
GROCERY_REVISION = "fc80ba90f803d79d0383df52c5a4ac5de99ff6fc"
GROCERY_RAW_URL = (
    f"https://raw.githubusercontent.com/marcusklasson/GroceryStoreDataset/{GROCERY_REVISION}/"
)
DEFAULT_CLASS_IDS = (6, 16, 63)  # Banana, Orange, Cucumber.
SPLITS = ("train", "val", "test")


def _fetch(relative_path: str, *, max_bytes: int = 12_000_000) -> bytes:
    url = GROCERY_RAW_URL + quote(relative_path, safe="/")
    try:
        with urlopen(url, timeout=30) as response:
            payload = response.read(max_bytes + 1)
    except (OSError, URLError) as exc:
        raise RuntimeError(f"Não foi possível baixar {url}: {exc}") from exc
    if not payload or len(payload) > max_bytes:
        raise ValueError(f"Arquivo vazio ou maior que o limite: {relative_path}")
    return payload


def _positive_limit(value: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{name} deve ser um inteiro positivo.")


def _read_classes(payload: bytes) -> dict[int, tuple[str, int]]:
    reader = csv.DictReader(io.StringIO(payload.decode("utf-8-sig")))
    required = {
        "Class Name (str)",
        "Class ID (int)",
        "Coarse Class ID (int)",
    }
    if not required.issubset(reader.fieldnames or ()):
        raise ValueError("classes.csv não contém o cabeçalho oficial esperado.")
    classes: dict[int, tuple[str, int]] = {}
    for row in reader:
        class_id = int(row["Class ID (int)"])
        coarse_id = int(row["Coarse Class ID (int)"])
        name = row["Class Name (str)"].strip()
        if class_id < 0 or coarse_id < 0 or not name or class_id in classes:
            raise ValueError("classes.csv contém uma classe inválida ou repetida.")
        classes[class_id] = (name, coarse_id)
    if not classes:
        raise ValueError("classes.csv está vazio.")
    return classes


def _read_split(
    payload: bytes, split: str, classes: dict[int, tuple[str, int]]
) -> list[tuple[str, int]]:
    rows: list[tuple[str, int]] = []
    seen: set[str] = set()
    for row in csv.reader(io.StringIO(payload.decode("utf-8-sig"))):
        if not row or not any(field.strip() for field in row):
            continue
        if len(row) != 3:
            raise ValueError(f"Linha inválida no manifesto {split}.txt.")
        source_path, fine_label, coarse_label = (value.strip() for value in row)
        segments = source_path.split("/")
        path = PurePosixPath(source_path)
        if (
            len(segments) < 3
            or segments[0] != split
            or any(part in ("", ".", "..") for part in segments)
            or any(character in source_path for character in ("\\", ":", "\x00"))
            or path.is_absolute()
            or path.suffix.lower() not in (".jpg", ".jpeg", ".png")
            or source_path in seen
        ):
            raise ValueError(f"Caminho inseguro, repetido ou fora do split: {source_path}")
        class_id, coarse_id = int(fine_label), int(coarse_label)
        if class_id not in classes or coarse_id != classes[class_id][1]:
            raise ValueError(f"Rótulo inconsistente em {split}.txt: {source_path}")
        seen.add(source_path)
        rows.append((source_path, class_id))
    if not rows:
        raise ValueError(f"O manifesto {split}.txt está vazio.")
    return rows


def download_grocery_subset(
    destination: Path,
    class_ids: tuple[int, ...] = DEFAULT_CLASS_IDS,
    max_train_per_class: int = 10,
    max_eval_per_class: int = 5,
) -> dict:
    """Download selected official images, preserving their train/val/test splits.

    ``destination`` must be absent or empty. Only training images belong in the
    recognition index. Prices in ``catalog.csv`` are fictional demo values.
    The return value is JSON-serializable and includes paths and image counts.
    """
    _positive_limit(max_train_per_class, "max_train_per_class")
    _positive_limit(max_eval_per_class, "max_eval_per_class")
    class_ids = tuple(class_ids)
    if (
        not class_ids
        or any(
            isinstance(value, bool) or not isinstance(value, int) or value < 0
            for value in class_ids
        )
        or len(set(class_ids)) != len(class_ids)
    ):
        raise ValueError("class_ids deve conter IDs inteiros distintos e não negativos.")
    destination = Path(destination).absolute()
    if destination.exists() and (not destination.is_dir() or any(destination.iterdir())):
        raise ValueError("O destino deve ser uma pasta vazia ou ainda não existir.")

    metadata = {
        name: _fetch(name, max_bytes=2_000_000)
        for name in ("LICENSE", "dataset/classes.csv", *(f"dataset/{s}.txt" for s in SPLITS))
    }
    classes = _read_classes(metadata["dataset/classes.csv"])
    missing = set(class_ids) - classes.keys()
    if missing:
        raise ValueError(f"Classes inexistentes: {sorted(missing)}")

    selection: list[tuple[str, str, int]] = []
    counts = {split: 0 for split in SPLITS}
    for split in SPLITS:
        limit = max_train_per_class if split == "train" else max_eval_per_class
        per_class: Counter[int] = Counter()
        rows = _read_split(metadata[f"dataset/{split}.txt"], split, classes)
        for source_path, class_id in rows:
            if class_id in class_ids and per_class[class_id] < limit:
                selection.append((split, source_path, class_id))
                per_class[class_id] += 1
                counts[split] += 1
        absent = [class_id for class_id in class_ids if not per_class[class_id]]
        if absent:
            raise ValueError(f"Classes sem imagens no split {split}: {absent}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "dataset": "Grocery Store Dataset",
        "repository": GROCERY_REPOSITORY,
        "revision": GROCERY_REVISION,
        "license": "MIT (arquivo LICENSE do repositório original)",
        "class_ids": list(class_ids),
        "counts": counts,
        "prices_are_demo": True,
        "metadata": {
            name: {
                "url": GROCERY_RAW_URL + name,
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
            for name, payload in metadata.items()
        },
        "images": [],
    }
    with TemporaryDirectory(prefix=".grocery-subset-", dir=destination.parent) as temporary:
        staging = Path(temporary) / "dataset"
        staging.mkdir()
        (staging / "LICENSE").write_bytes(metadata["LICENSE"])
        (staging / "metadata").mkdir()
        for name, payload in metadata.items():
            if name.startswith("dataset/"):
                (staging / "metadata" / PurePosixPath(name).name).write_bytes(payload)
        digest_splits: dict[str, str] = {}
        for index, (split, source_path, class_id) in enumerate(selection):
            relative_source = "dataset/" + source_path
            payload = _fetch(relative_source)
            if not (
                payload.startswith(b"\xff\xd8\xff") or payload.startswith(b"\x89PNG\r\n\x1a\n")
            ):
                raise ValueError(f"Resposta não é uma imagem JPEG/PNG: {source_path}")
            digest = hashlib.sha256(payload).hexdigest()
            if digest in digest_splits and digest_splits[digest] != split:
                raise ValueError(f"Imagem duplicada entre splits: {source_path}")
            digest_splits[digest] = split
            local_path = f"{split}/{class_id}/{index:04d}_{PurePosixPath(source_path).name}"
            target = staging / Path(local_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
            manifest["images"].append(
                {
                    "split": split,
                    "class_id": class_id,
                    "source_path": source_path,
                    "local_path": local_path,
                    "source_url": GROCERY_RAW_URL + quote(relative_source, safe="/"),
                    "sha256": digest,
                }
            )
        with (staging / "catalog.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(("sku", "name", "price"))
            for class_id in class_ids:
                writer.writerow(
                    (
                        str(class_id),
                        classes[class_id][0].replace("-", " "),
                        format(Decimal("1.00"), ".2f"),
                    )
                )
        (staging / "source_manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        if destination.exists():
            destination.rmdir()  # Fails safely if another process populated it.
        staging.rename(destination)
    return {
        "destination": str(destination),
        "catalog_path": str(destination / "catalog.csv"),
        "manifest_path": str(destination / "source_manifest.json"),
        "revision": GROCERY_REVISION,
        "class_ids": list(class_ids),
        "counts": counts,
        "total_images": sum(counts.values()),
    }
