"""A balanced classification subset from official RPC v5 annotations and images.

Official checkout validation/test scenes contain many objects. This adapter uses
their annotated boxes to prepare single-item crops: it does not add a detector.
"""

from __future__ import annotations

import csv
import hashlib
import html
import io
import json
import math
import time
import zipfile
from collections import Counter, defaultdict
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import urlopen

from PIL import Image

RPC_VERSION = 5
RPC_SOURCE = "https://www.kaggle.com/datasets/diyer22/retail-product-checkout-dataset"
RPC_PROJECT = "https://rpc-dataset.github.io/"
RPC_API = "https://www.kaggle.com/api/v1/datasets/download/diyer22/retail-product-checkout-dataset/"
RPC_LICENSE = "CC BY-NC-SA 4.0"
SPLITS = ("train", "val", "test")
GROUP_NAMES = {
    "puffed_food": "Salgadinhos",
    "dried_fruit": "Frutas secas",
    "dried_food": "Alimentos secos",
    "instant_drink": "Bebidas instantâneas",
    "instant_noodles": "Macarrão instantâneo",
    "dessert": "Sobremesas e biscoitos",
    "drink": "Bebidas",
    "alcohol": "Bebidas alcoólicas",
    "milk": "Leites e derivados",
    "canned_food": "Enlatados",
    "chocolate": "Chocolates",
    "gum": "Chicletes",
    "candy": "Balas",
    "seasoner": "Temperos e molhos",
    "personal_hygiene": "Higiene pessoal",
    "tissue": "Lenços e papéis",
    "stationery": "Papelaria",
}


def _safe_name(name: str) -> str:
    if (
        not isinstance(name, str)
        or not name
        or name in {".", ".."}
        or PurePosixPath(name).name != name
        or any(character in name for character in "\\:/\x00")
    ):
        raise ValueError(f"Nome de arquivo RPC inválido: {name!r}")
    return name


def _download_file(relative: str, limit: int) -> bytes:
    # Encode '/' in fileName: Kaggle's per-file route is a single URL segment.
    url = RPC_API + quote(relative, safe="") + f"?datasetVersionNumber={RPC_VERSION}"
    return _download_url(url, relative, limit)


def _download_url(url: str, relative: str, limit: int) -> bytes:
    for attempt in range(4):
        try:
            with urlopen(url, timeout=45) as response:
                payload = response.read(limit + 1)
            if not payload or len(payload) > limit:
                raise ValueError(f"Arquivo RPC vazio ou maior que o limite: {relative}")
            if payload.startswith(b"PK"):
                with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                    members = archive.infolist()
                    if (
                        len(members) != 1
                        or members[0].filename != PurePosixPath(relative).name
                        or members[0].file_size > 80_000_000
                    ):
                        raise ValueError(f"Arquivo ZIP RPC inesperado: {relative}")
                    payload = archive.read(members[0])
            return payload
        except HTTPError as exc:
            if exc.code == 429:
                raise RuntimeError(
                    "O provedor limitou requisições (HTTP 429). "
                    "Instalação interrompida; cache preservado para retomar mais tarde."
                ) from exc
            if exc.code not in {500, 502, 503, 504} or attempt == 3:
                raise RuntimeError(f"Download RPC falhou (HTTP {exc.code}): {relative}") from exc
        except (OSError, URLError) as exc:
            if attempt == 3:
                raise RuntimeError(f"Download RPC falhou: {relative}: {exc}") from exc
        time.sleep(2**attempt)
    raise RuntimeError(f"Download RPC falhou: {relative}")


def _cache_file(cache: Path, relative: str, limit: int, source_url: str | None = None) -> bytes:
    # All components originate in validated official metadata, never ZIP paths.
    target = cache.joinpath(*relative.split("/"))
    if target.is_file():
        return target.read_bytes()
    payload = (
        _download_url(source_url, relative, limit)
        if source_url
        else _download_file(relative, limit)
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".part")
    temporary.write_bytes(payload)
    temporary.replace(target)
    return payload


def _categories(document: dict) -> dict[int, dict]:
    categories = {}
    for category in document["categories"]:
        category_id = category["id"]
        if (
            type(category_id) is not int
            or category_id < 1
            or category_id in categories
            or category.get("supercategory") not in GROUP_NAMES
        ):
            raise ValueError("Categorias RPC inválidas ou repetidas.")
        categories[category_id] = category
    if not categories:
        raise ValueError("O RPC não contém categorias.")
    return categories


def _select_samples(document: dict, split: str, limit: int, seed: int) -> list[dict]:
    categories = _categories(document)
    images = {}
    for image in document["images"]:
        _safe_name(image["file_name"])
        if image["id"] in images or image["width"] <= 0 or image["height"] <= 0:
            raise ValueError("Imagens RPC inválidas ou repetidas.")
        images[image["id"]] = image
    by_class = defaultdict(list)
    seen_ids = set()
    for annotation in document["annotations"]:
        category_id, image_id = annotation["category_id"], annotation["image_id"]
        if category_id not in categories or image_id not in images:
            raise ValueError("Anotação RPC aponta para imagem/classe inexistente.")
        if type(annotation["id"]) is not int or annotation["id"] in seen_ids:
            raise ValueError("IDs de anotação RPC inválidos ou repetidos.")
        seen_ids.add(annotation["id"])
        bbox = annotation["bbox"]
        if (
            len(bbox) != 4
            or not all(isinstance(value, (int, float)) and math.isfinite(value) for value in bbox)
            or bbox[0] < 0
            or bbox[1] < 0
            or bbox[2] <= 0
            or bbox[3] <= 0
            or bbox[0] >= images[image_id]["width"]
            or bbox[1] >= images[image_id]["height"]
        ):
            raise ValueError("Bounding box RPC inválida.")
        if annotation.get("iscrowd", 0):
            continue
        by_class[category_id].append(annotation)

    selected = []
    for category_id in sorted(categories):

        def order(annotation):
            image = images[annotation["image_id"]]
            # Prefer easy checkout scenes, but still preserve official split boundaries.
            easy = image.get("level", "easy") != "easy"
            token = f"{seed}:{split}:{annotation['id']}".encode()
            return easy, hashlib.sha256(token).hexdigest()

        candidates = sorted(by_class[category_id], key=order)
        used_images = set()
        for annotation in candidates:
            image_id = annotation["image_id"]
            if image_id in used_images:
                continue
            used_images.add(image_id)
            selected.append({"split": split, "image": images[image_id], "annotation": annotation})
            if len(used_images) == limit:
                break
        if len(used_images) != limit:
            raise ValueError(f"RPC {split}: imagens insuficientes para a classe {category_id}.")
    return selected


def _crop(payload: bytes, bbox: list[float], width: int, height: int) -> bytes:
    with Image.open(io.BytesIO(payload)) as image:
        if image.size != (width, height):
            raise ValueError("As dimensões da imagem RPC diferem das anotações.")
        x, y, box_width, box_height = bbox
        # Small context margin; val/test use annotated crops, not predicted detections.
        padding = 0.05 * max(box_width, box_height)
        rectangle = (
            max(0, math.floor(x - padding)),
            max(0, math.floor(y - padding)),
            min(width, math.ceil(x + box_width + padding)),
            min(height, math.ceil(y + box_height + padding)),
        )
        crop = image.convert("RGB").crop(rectangle)
        crop.thumbnail((512, 512), Image.Resampling.LANCZOS)
        output = io.BytesIO()
        crop.save(output, format="JPEG", quality=95)
        return output.getvalue()


def write_preview(directory: Path, manifest: dict) -> None:
    """A local contact catalog using the existing crop files, without modifying images."""
    representatives = {}
    for sample in sorted(manifest["images"], key=lambda sample: sample["local_path"]):
        if sample["split"] == "train":
            representatives.setdefault(sample["sku"], sample)
    cards = []
    for sku, sample in sorted(representatives.items()):
        cards.append(
            f'<figure><a href="{html.escape(sample["local_path"], quote=True)}">'
            f'<img loading="lazy" src="{html.escape(sample["local_path"], quote=True)}" '
            f'alt="{html.escape(sku)}"></a><figcaption>{html.escape(sku)}</figcaption></figure>'
        )
    page = (
        '<!doctype html><html lang="pt-BR"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        "<title>RPC — catálogo visual de testes</title><style>"
        "body{font:16px system-ui;background:#f4f6f8;color:#17212e;margin:32px}"
        "main{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:16px}"
        "figure{margin:0;background:white;padding:12px;border-radius:12px;text-align:center}"
        "img{width:100%;height:170px;object-fit:contain}figcaption{padding:10px 0 0}"
        "</style><h1>RPC — catálogo visual de testes</h1>"
        "<p>200 produtos de mercado. Um exemplo de treino por SKU. "
        "Uso em pesquisa e testes não comerciais: CC BY-NC-SA 4.0.</p>"
        "<p>Consulte catalog.csv para os grupos e metadata/original_product_names.json "
        "para os nomes originais. Clique na foto para ampliar.</p><main>"
        + "".join(cards)
        + "</main></html>"
    )
    (Path(directory) / "preview.html").write_text(page, encoding="utf-8")


def download_rpc_subset(
    destination: Path,
    cache_dir: Path = Path(".cache/rpc"),
    train_per_class: int = 12,
    eval_per_class: int = 4,
    workers: int = 8,
    seed: int = 42,
    progress: Callable[[str], None] | None = None,
    source: str = "huggingface",
) -> dict:
    """Install all 200 RPC SKUs as a bounded, deterministic crop subset.

    Downloads are cached for retries. Original galleries and catalogs are never
    overwritten. Prices are demonstration placeholders, not prices from RPC.
    """
    for name, value in {
        "train_per_class": train_per_class,
        "eval_per_class": eval_per_class,
        "workers": workers,
    }.items():
        if type(value) is not int or value < 1:
            raise ValueError(f"{name} deve ser um inteiro positivo.")
    if workers > 16 or train_per_class > 100 or eval_per_class > 50:
        raise ValueError("Limites máximos: workers=16, train=100, eval=50 por classe.")
    if type(seed) is not int:
        raise ValueError("seed deve ser inteiro.")
    if source not in {"kaggle", "huggingface"}:
        raise ValueError("source deve ser kaggle ou huggingface.")
    destination = Path(destination).resolve()
    cache = Path(cache_dir).resolve() / f"v{RPC_VERSION}"
    if destination.exists():
        raise ValueError("O destino RPC já existe; use uma pasta nova para preservar os dados.")
    if cache == destination or cache.is_relative_to(destination):
        raise ValueError("O cache deve ficar fora do destino RPC.")
    documents, raw_metadata, selection = {}, {}, []
    for split in SPLITS:
        if progress:
            progress(f"RPC: lendo anotações oficiais de {split} (v{RPC_VERSION})")
        filename = f"instances_{split}2019.json"
        raw_metadata[filename] = _cache_file(cache, filename, 20_000_000)
        documents[split] = json.loads(raw_metadata[filename])
    source_urls, mirror_info = {}, {}
    if source == "huggingface":
        from caixa_inteligente.rpc_mirror import prepare_sources

        documents, source_urls, mirror_info = prepare_sources(
            documents, cache, train_per_class, eval_per_class, progress, seed=seed
        )
    for split in SPLITS:
        selection.extend(
            _select_samples(
                documents[split],
                split,
                train_per_class if split == "train" else eval_per_class,
                seed,
            )
        )
    categories = _categories(documents["train"])
    if any(_categories(document) != categories for document in documents.values()):
        raise ValueError("Categorias RPC inconsistentes entre splits.")
    grouped = defaultdict(list)
    source_splits = {}
    for sample in selection:
        split, filename = sample["split"], sample["image"]["file_name"]
        if filename in source_splits and source_splits[filename] != split:
            raise ValueError("A mesma imagem RPC apareceu em mais de um split.")
        source_splits[filename] = split
        grouped[f"{split}2019/{filename}"].append(sample)

    manifest = {
        "dataset": "RPC single-item crop subset",
        "source": RPC_SOURCE,
        "project": RPC_PROJECT,
        "dataset_version": RPC_VERSION,
        "image_distribution": source,
        "mirror": mirror_info,
        "license": RPC_LICENSE,
        "seed": seed,
        "limits": {"train_per_class": train_per_class, "eval_per_class": eval_per_class},
        "classes": len(categories),
        "supercategories": dict(Counter(c["supercategory"] for c in categories.values())),
        "classification_uses_ground_truth_boxes": True,
        "crop": {"padding_fraction": 0.05, "max_dimension": 512, "jpeg_quality": 95},
        "prices_are_demo": True,
        "metadata_sha256": {
            name: hashlib.sha256(data).hexdigest() for name, data in raw_metadata.items()
        },
        "images": [],
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".rpc-preparing-", dir=destination.parent) as temporary:
        staging = Path(temporary) / "dataset"
        staging.mkdir()
        metadata_dir = staging / "metadata"
        metadata_dir.mkdir()
        for name, payload in raw_metadata.items():
            (metadata_dir / name).write_bytes(payload)
        (metadata_dir / "categories.json").write_text(
            json.dumps(list(categories.values()), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (metadata_dir / "original_product_names.json").write_text(
            json.dumps(
                documents["train"].get("__raw_Chinese_name_df", []), ensure_ascii=False, indent=2
            ),
            encoding="utf-8",
        )
        digest_splits = {}
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(_cache_file, cache, name, 12_000_000, source_urls.get(name)): name
                for name in grouped
            }
            try:
                for finished, future in enumerate(as_completed(futures), 1):
                    source_name, payload = futures[future], future.result()
                    digest = hashlib.sha256(payload).hexdigest()
                    for sample in grouped[source_name]:
                        split, annotation, image = (
                            sample["split"],
                            sample["annotation"],
                            sample["image"],
                        )
                        if digest in digest_splits and digest_splits[digest] != split:
                            raise ValueError(
                                "Imagem RPC idêntica entre splits; instalação interrompida."
                            )
                        digest_splits[digest] = split
                        sku = f"rpc-{annotation['category_id']:03d}"
                        relative = f"{split}/{sku}/{annotation['id']}.jpg"
                        crop = _crop(payload, annotation["bbox"], image["width"], image["height"])
                        target = staging / relative
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_bytes(crop)
                        manifest["images"].append(
                            {
                                "split": split,
                                "sku": sku,
                                "category_id": annotation["category_id"],
                                "annotation_id": annotation["id"],
                                "image_id": image["id"],
                                "source_file": source_name,
                                "source_sha256": digest,
                                "bbox": annotation["bbox"],
                                "local_path": relative,
                                "sha256": hashlib.sha256(crop).hexdigest(),
                            }
                        )
                    if progress and (finished % 100 == 0 or finished == len(futures)):
                        progress(f"RPC: {finished}/{len(futures)} imagens-fonte preparadas")
            except BaseException:
                for pending in futures:
                    pending.cancel()
                raise
        with (staging / "catalog.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["sku", "name", "price"])
            for category_id, category in sorted(categories.items()):
                group = GROUP_NAMES[category["supercategory"]]
                writer.writerow(
                    [f"rpc-{category_id:03d}", f"{group} / RPC {category_id:03d}", "1.00"]
                )
        attribution = (
            "RPC: A Large-Scale Retail Product Checkout Dataset\n"
            "Xiu-Shen Wei, Quan Cui, Lei Yang, Peng Wang, Lingqiao Liu, Jian Yang.\n"
            f"Original project: {RPC_PROJECT}\nOriginal distribution: {RPC_SOURCE}\n"
            f"License: {RPC_LICENSE}\nhttps://creativecommons.org/licenses/by-nc-sa/4.0/\n"
            "Research/test subset: ground-truth box crops with 5% padding, resized to max 512px.\n"
            "This derived dataset is for noncommercial research/testing under the same license.\n"
            "Product names are demonstration identifiers. All prices are fictional.\n"
        )
        (staging / "LICENSE-RPC.txt").write_text(attribution, encoding="utf-8")
        manifest["images"].sort(key=lambda sample: sample["local_path"])
        manifest["counts"] = dict(Counter(sample["split"] for sample in manifest["images"]))
        write_preview(staging, manifest)
        (staging / "source_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        staging.rename(destination)
    return {
        "destination": str(destination),
        "classes": len(categories),
        "supercategories": len(manifest["supercategories"]),
        "counts": manifest["counts"],
        "total_images": len(selection),
        "source_images": len(grouped),
        "catalog_path": str(destination / "catalog.csv"),
        "license": RPC_LICENSE,
        "protocol": "classification with ground-truth object crops, not object detection",
    }
