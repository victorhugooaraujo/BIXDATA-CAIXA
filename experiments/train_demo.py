"""Train only on train split; select ridge strength on validation; report held-out tests."""

import csv
import hashlib
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
SOURCE = Path(os.environ.get("CAIXA_DATA_ROOT", ROOT))
os.environ.setdefault("TORCH_HOME", str(SOURCE / ".cache/torch"))

from caixa_inteligente.demo.classifier import ProductClassifier  # noqa: E402
from caixa_inteligente.demo.dataset import validate_disjoint  # noqa: E402
from caixa_inteligente.vision import DINOV2_SIGNATURE, DinoV2Encoder, _preprocess_image  # noqa: E402


def main():
    import torch

    torch.set_num_threads(4)
    torch.manual_seed(42)
    folder = ROOT / "artifacts/demo-training"
    dataset = json.loads((folder / "dataset.json").read_text(encoding="utf-8"))
    samples = [
        {**s, "group": "user", "path": str(folder / f"{s['id']}-crop.jpg")}
        for s in dataset["samples"]
    ]
    for split in ["train", "val", "test"]:
        for path in sorted((SOURCE / "data/rpc" / split).glob("*/*")):
            if path.suffix.lower() in {".jpg", ".jpeg", ".png"}:
                samples.append(
                    {
                        "id": f"rpc/{split}/{path.parent.name}/{path.name}",
                        "sku": path.parent.name,
                        "split": split,
                        "group": "public",
                        "path": str(path),
                    }
                )
    if sum(s["group"] == "public" for s in samples) != 4000:
        raise ValueError("Dataset RPC incompleto: esperadas 2.400/800/800 imagens.")
    for split in ["val", "test"]:
        for path in sorted((SOURCE / "data/grocery" / split).glob("*/*")):
            if path.suffix.lower() in {".jpg", ".jpeg", ".png"}:
                samples.append(
                    {
                        "id": f"unknown/{split}/{path.parent.name}/{path.name}",
                        "sku": None,
                        "split": split,
                        "group": "unknown",
                        "path": str(path),
                    }
                )
    for sample in samples:
        sample["sha256"] = hashlib.sha256(Path(sample["path"]).read_bytes()).hexdigest()
    validate_disjoint(samples)
    fingerprint = hashlib.sha256(json.dumps(samples, sort_keys=True).encode()).hexdigest()
    cache = folder / f"features-{fingerprint[:16]}.npz"
    start = time.perf_counter()
    if cache.exists():
        with np.load(cache, allow_pickle=False) as data:
            if str(data["fingerprint"]) != fingerprint:
                raise ValueError("Cache de features pertence a outro dataset.")
            features = data["features"]
    else:
        encoder = DinoV2Encoder("cuda")
        model = encoder._load_model()
        chunks = []
        for offset in range(0, len(samples), 48):
            batch = torch.stack(
                [_preprocess_image(Path(s["path"])) for s in samples[offset : offset + 48]]
            )
            with torch.inference_mode():
                encoded = model(batch.to("cuda"))
                encoded = torch.nn.functional.normalize(encoded, dim=1)
            chunks.append(encoded.cpu().numpy())
            print(f"features {min(offset + 48, len(samples))}/{len(samples)}", flush=True)
        features = np.concatenate(chunks)
        np.savez_compressed(cache, features=features, fingerprint=np.array(fingerprint))
    train = [i for i, s in enumerate(samples) if s["split"] == "train"]
    labels = [samples[i]["sku"] for i in train]
    validation, heads = [], []
    for strength in [0.01, 0.1, 1.0, 10.0]:
        head = ProductClassifier.fit(features[train], labels, regularization=strength)
        metrics = {}
        for group in ["user", "public"]:
            subset = [
                i for i, s in enumerate(samples) if s["split"] == "val" and s["group"] == group
            ]
            correct = sum(head.rank(features[i])[0]["sku"] == samples[i]["sku"] for i in subset)
            metrics[group] = correct / len(subset)
        validation.append({"regularization": strength, **metrics})
        heads.append(head)
    best = max(
        range(len(heads)), key=lambda i: (validation[i]["user"] + validation[i]["public"]) / 2
    )
    head = heads[best]
    head.save(folder / "classifier.npz", signature=DINOV2_SIGNATURE)
    results = []
    for i, sample in enumerate(samples):
        if sample["split"] != "train":
            ranked = head.rank(features[i])
            results.append(
                {k: sample[k] for k in ["id", "sku", "split", "group"]}
                | {
                    "predicted": ranked[0]["sku"],
                    "similarity": ranked[0]["similarity"],
                    "margin": ranked[0]["score"] - ranked[1]["score"],
                    "top3": [r["sku"] for r in ranked[:3]],
                }
            )
    metrics = {}
    for group in ["user", "public", "unknown"]:
        for split in ["val", "test"]:
            rows = [r for r in results if r["group"] == group and r["split"] == split]
            metrics[f"{group}_{split}"] = {
                "images": len(rows),
                "correct": sum(r["sku"] == r["predicted"] for r in rows),
                "top3_correct": sum(r["sku"] in r["top3"] for r in rows),
            }
            if group == "unknown":
                metrics[f"{group}_{split}"] = {
                    "images": len(rows),
                    "automatic_acceptances": 0,
                    "policy": "Every image requires review; no unknown-rejection calibration claim",
                }
    catalog = list(dataset["catalog"])
    with (SOURCE / "data/rpc/catalog.csv").open(encoding="utf-8", newline="") as stream:
        catalog += [
            {"sku": r["sku"], "name": r["name"], "price_cents": 100, "size": None}
            for r in csv.DictReader(stream)
        ]
    (folder / "catalog.json").write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    report = {
        "schema": 1,
        "encoder": json.loads(DINOV2_SIGNATURE),
        "training_samples": len(train),
        "training_per_group": dict(Counter(samples[i]["group"] for i in train)),
        "classes": len(head.skus),
        "classifier_sha256": hashlib.sha256((folder / "classifier.npz").read_bytes()).hexdigest(),
        "dataset_fingerprint": fingerprint,
        "validation": validation,
        "selected_regularization": validation[best]["regularization"],
        "metrics": metrics,
        "seconds": time.perf_counter() - start,
        "predictions": results,
        "limitations": [
            "Same physical products and session in user splits",
            "RPC research license; no commercial clearance",
            "No barcode used",
            "Classifier metrics use prepared crops; detector evaluated separately",
            "No commercial reliability claim",
        ],
    }
    (folder / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "classes": len(head.skus),
                "train": len(train),
                "validation": validation,
                "metrics": metrics,
            },
            indent=2,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
