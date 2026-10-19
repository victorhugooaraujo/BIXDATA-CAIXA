"""Validate dataset recognition without MySQL or manual product registration."""

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
os.environ.setdefault("TORCH_HOME", str(ROOT / ".cache/torch"))

from caixa_inteligente.cli import image_samples  # noqa: E402
from caixa_inteligente.evaluation import recognition_metrics  # noqa: E402
from caixa_inteligente.hybrid import TextGallery, fuse  # noqa: E402
from caixa_inteligente.ocr import OcrReader, evidence_text  # noqa: E402
from caixa_inteligente.vision import DinoV2Encoder, Gallery  # noqa: E402


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def decision(visual, textual, expected, known):
    fused = fuse(visual, textual, 0.2)
    accepted = None
    # Existing visual baseline thresholds only; no new hybrid gate is calibrated here.
    if len(visual) >= 2 and visual[0].similarity >= 0.75:
        if visual[0].similarity - visual[1].similarity >= 0.05:
            accepted = visual[0].sku
    return {
        "expected": expected,
        "is_known": expected in known,
        "visual_prediction": visual[0].sku,
        "text_prediction": textual[0].sku if textual[0].similarity > 0 else None,
        "hybrid_prediction": fused[0]["sku"],
        "accepted": accepted,
        "candidates": fused[:5],
    }


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=Path("data/rpc"))
    parser.add_argument("--gallery", type=Path, default=Path("artifacts/hybrid-rpc-12visual-3text"))
    parser.add_argument("--cache", type=Path, default=Path(".cache/ocr-rpc-v1"))
    parser.add_argument(
        "--report", type=Path, default=Path("artifacts/recognition-validation.json")
    )
    parser.add_argument("--split", choices=["val", "test"], default="test")
    args = parser.parse_args()
    import torch

    torch.set_num_threads(4)
    manifest = json.loads((args.gallery / "manifest.json").read_text(encoding="utf-8"))
    for key, filename in [("visual_sha256", "visual.npz"), ("text_sha256", "text.json")]:
        if sha(args.gallery / filename) != manifest[key]:
            raise ValueError("Checksum da galeria divergente.")
    encoder = DinoV2Encoder("cuda")
    reader = OcrReader(args.cache)
    visual = Gallery.load(args.gallery / "visual.npz", expected_signature=encoder.signature)
    textual = TextGallery.load(args.gallery / "text.json", reader.signature)
    classes = sorted({reference["sku"] for reference in textual.references})
    if len(classes) != 200:
        raise ValueError("Este protocolo RPC espera 200 SKUs.")
    withheld = set(classes[::10])  # Fixed before looking at query scores: 20 unknown SKUs.
    known = set(classes) - withheld
    open_text = TextGallery(
        [ref for ref in textual.references if ref["sku"] in known], textual.signature
    )
    train_hashes = {sha(path) for _, path in image_samples(args.dataset / "train")}
    samples = image_samples(args.dataset / args.split)
    closed_rows, open_rows, hashes = [], [], []
    started = perf_counter()
    for index, (expected, path) in enumerate(samples, 1):
        digest = sha(path)
        if digest in train_hashes:
            raise ValueError("Consulta idêntica a uma imagem de treino.")
        hashes.append(digest)
        text = evidence_text(reader.read(path))
        ranked = visual.rank(encoder.encode(path))
        closed = decision(ranked, textual.rank(text), expected, set(classes))
        opened = decision(
            [candidate for candidate in ranked if candidate.sku in known],
            open_text.rank(text),
            expected,
            known,
        )
        for rows, result in [(closed_rows, closed), (open_rows, opened)]:
            rows.append({"path": str(path.resolve()), "sha256": digest, **result})
        if index % 100 == 0:
            print(f"Consultas: {index}/{len(samples)}", flush=True)
    report = {
        "dataset": str(args.dataset.resolve()),
        "split": args.split,
        "manual_registration": False,
        "database_access": False,
        "catalog_source": "dataset train labels",
        "text_weight": 0.2,
        "visual_thresholds": {"similarity": 0.75, "margin": 0.05},
        "gallery_manifest": manifest,
        "withheld_skus": sorted(withheld),
        "open_text_reference_count": len(open_text.references),
        "train_unique_hashes": len(train_hashes),
        "query_unique_hashes": len(set(hashes)),
        "train_query_exact_overlap": 0,
        "seconds_with_cached_ocr": perf_counter() - started,
        "peak_torch_cuda_allocated_bytes": torch.cuda.max_memory_allocated(),
        "test_previously_used_for_visual_baseline": True,
        "closed_set": recognition_metrics(closed_rows),
        "open_set": recognition_metrics(open_rows),
        "predictions": {"closed_set": closed_rows, "open_set": open_rows},
        "limitations": [
            "Crops with ground-truth boxes; no automatic detection.",
            "No verified brand/size/variant attribute ground truth.",
            "Hybrid automatic rejection remains uncalibrated.",
            "Frozen encoder was not retrained after withholding gallery SKUs.",
        ],
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                key: value
                for key, value in report.items()
                if key not in {"predictions", "gallery_manifest"}
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
