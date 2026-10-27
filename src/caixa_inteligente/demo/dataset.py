"""Small dataset primitives with explicit leakage and archive boundaries."""

import hashlib
import io
import json
import math
import random
import zipfile
from collections import defaultdict
from pathlib import Path, PurePosixPath


def prepare_archive(path, annotations, output):
    """Reproduce crops from reviewed labels; never execute or extract archive paths."""
    from PIL import Image, ImageOps

    path, output = Path(path), Path(output)
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    if digest != annotations["source_zip_sha256"]:
        raise ValueError("ZIP diferente do conjunto anotado.")
    with zipfile.ZipFile(path) as archive:
        members = {PurePosixPath(m.filename).stem: m for m in safe_image_members(archive)}
        output.mkdir(parents=True, exist_ok=True)
        (output / "scenes").mkdir(exist_ok=True)
        for sample in annotations["samples"]:
            identifier = sample["id"]
            if not identifier or any(
                c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
                for c in identifier
            ):
                raise ValueError("Identificador de amostra inválido.")
            raw = archive.read(members[identifier.split("_", 1)[1]])
            if hashlib.sha256(raw).hexdigest() != sample["source_sha256"]:
                raise ValueError("Imagem diferente da anotação revisada.")
            with Image.open(io.BytesIO(raw)) as source:
                if source.width * source.height > 30_000_000:
                    raise ValueError("Imagem excede limite de pixels.")
                image = ImageOps.exif_transpose(source).convert("RGB")
            box = [value * image.size[i % 2] for i, value in enumerate(sample["box"])]
            crop = crop_box(image, box)
            crop.thumbnail((512, 512))
            crop.save(output / f"{identifier}-crop.jpg", quality=95)
            image.thumbnail((1600, 1600))
            image.save(output / "scenes" / f"{identifier}.jpg", quality=95)
    (output / "dataset.json").write_text(
        json.dumps(annotations, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def validate_disjoint(samples):
    observed = {}
    for sample in samples:
        split = sample["split"]
        if split not in {"train", "val", "test"}:
            raise ValueError("split desconhecido")
        previous = observed.setdefault(sample["sha256"], split)
        if previous != split:
            raise ValueError("Imagem idêntica em mais de um split.")


def assign_splits(samples: list[dict], seed: int = 42) -> list[dict]:
    hashes, identifiers = set(), set()
    groups = defaultdict(list)
    for sample in samples:
        if sample["sha256"] in hashes or sample["id"] in identifiers:
            raise ValueError("Amostra duplicada: rótulos/splits não podem compartilhar imagem.")
        hashes.add(sample["sha256"])
        identifiers.add(sample["id"])
        groups[sample["sku"]].append(dict(sample))
    output = []
    for sku, items in sorted(groups.items()):
        if len(items) < 4:
            raise ValueError(f"{sku}: são necessárias ao menos quatro imagens independentes.")
        items.sort(key=lambda item: item["id"])
        random.Random(f"{seed}:{sku}").shuffle(items)
        test_count = 2 if len(items) >= 5 else 1
        for index, item in enumerate(items):
            item["split"] = (
                "test" if index < test_count else "val" if index == test_count else "train"
            )
            output.append(item)
    return sorted(output, key=lambda item: item["id"])


def crop_box(image, box, context: float = 0.05):
    if len(box) != 4 or not all(math.isfinite(float(value)) for value in box):
        raise ValueError("Caixa deve conter quatro coordenadas finitas.")
    left, top, right, bottom = map(float, box)
    if right <= left or bottom <= top or not math.isfinite(context) or not 0 <= context <= 0.5:
        raise ValueError("Caixa ou contexto inválido.")
    dx, dy = (right - left) * context, (bottom - top) * context
    bounds = (
        max(0, math.floor(left - dx)),
        max(0, math.floor(top - dy)),
        min(image.width, math.ceil(right + dx)),
        min(image.height, math.ceil(bottom + dy)),
    )
    if bounds[2] <= bounds[0] or bounds[3] <= bounds[1]:
        raise ValueError("Caixa fora da imagem.")
    return image.crop(bounds)


def safe_image_members(archive):
    members, total = [], 0
    for member in archive.infolist():
        if member.is_dir():
            continue
        path = PurePosixPath(member.filename.replace("\\", "/"))
        if path.is_absolute() or ".." in path.parts or any(":" in part for part in path.parts):
            raise ValueError("Arquivo contém caminho inseguro.")
        if path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".heic", ".heif"}:
            continue
        total += member.file_size
        if member.file_size > 100_000_000 or total > 2_000_000_000 or len(members) >= 500:
            raise ValueError("Arquivo excede o limite de imagens/bytes.")
        members.append(member)
    return members
