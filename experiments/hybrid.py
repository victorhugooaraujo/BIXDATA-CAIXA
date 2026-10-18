"""Dataset-only, paired visual/OCR experiments; no checkout or price inference."""

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
from caixa_inteligente.hybrid import TextGallery, fuse  # noqa: E402
from caixa_inteligente.ocr import OcrReader, evidence_text  # noqa: E402
from caixa_inteligente.vision import DinoV2Encoder, Gallery  # noqa: E402


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["index", "recognize", "evaluate"])
    parser.add_argument("--dataset", type=Path, default=Path("data/rpc"))
    parser.add_argument("--gallery", type=Path, default=Path("artifacts/hybrid-v1"))
    parser.add_argument("--cache", type=Path, default=Path(".cache/ocr"))
    parser.add_argument("--references-per-sku", type=int, default=3)
    parser.add_argument("--queries-per-sku", type=int, default=4)
    parser.add_argument("--device", choices=["cuda", "cpu"], default="cuda")
    parser.add_argument("--image", type=Path)
    parser.add_argument("--split", choices=["val", "test"], default="val")
    parser.add_argument("--report", type=Path, default=Path("artifacts/hybrid-validation.json"))
    parser.add_argument("--text-weight", type=float, default=0.2)
    args = parser.parse_args()
    if not 0 <= args.text_weight <= 1:
        parser.error("--text-weight deve estar entre 0 e 1")
    if not 1 <= args.references_per_sku <= 100:
        parser.error("--references-per-sku deve estar entre 1 e 100")
    if not 1 <= args.queries_per_sku <= 100:
        parser.error("--queries-per-sku deve estar entre 1 e 100")
    if args.command == "recognize" and args.image is None:
        parser.error("recognize exige --image")

    import torch

    torch.set_num_threads(4)
    encoder = DinoV2Encoder(device=args.device)
    reader = OcrReader(args.cache)
    if args.command == "index":
        if args.gallery.exists():
            raise ValueError(
                "Destino já existe; escolha outra galeria para preservar experimentos."
            )
        counts = {}
        samples = []
        for sku, path in image_samples(args.dataset / "train"):
            counts[sku] = counts.get(sku, 0) + 1
            if counts[sku] <= args.references_per_sku:
                samples.append((sku, path))
        references, vectors = [], []
        for index, (sku, path) in enumerate(samples, 1):
            evidence = reader.read(path)
            references.append(
                {
                    "sku": sku,
                    "sha256": evidence["sha256"],
                    "text": evidence_text(evidence),
                    "path": str(path.resolve()),
                }
            )
            vectors.append(encoder.encode(path))
            if index % 50 == 0:
                print(f"Referências: {index}/{len(samples)}", flush=True)
        import numpy as np

        args.gallery.mkdir(parents=True)
        Gallery([sku for sku, _ in samples], np.stack(vectors), encoder.signature).save(
            args.gallery / "visual.npz"
        )
        TextGallery(references, reader.signature).save(args.gallery / "text.json")
        write(
            args.gallery / "manifest.json",
            {
                "schema": 1,
                "dataset": str(args.dataset.resolve()),
                "source_split": "train",
                "classes": len(counts),
                "references": len(samples),
                "references_with_text": sum(bool(ref["text"]) for ref in references),
                "visual_sha256": sha(args.gallery / "visual.npz"),
                "text_sha256": sha(args.gallery / "text.json"),
                "encoder": encoder.signature,
                "ocr": reader.signature,
            },
        )
        print((args.gallery / "manifest.json").read_text(encoding="utf-8"))
        return

    manifest = json.loads((args.gallery / "manifest.json").read_text(encoding="utf-8"))
    for key, filename in [("visual_sha256", "visual.npz"), ("text_sha256", "text.json")]:
        if sha(args.gallery / filename) != manifest[key]:
            raise ValueError("Checksum da galeria divergente.")
    visual = Gallery.load(args.gallery / "visual.npz", expected_signature=encoder.signature)
    textual = TextGallery.load(args.gallery / "text.json", reader.signature)
    reference_hashes = {ref["sha256"] for ref in textual.references}
    samples = (
        [(None, args.image)]
        if args.command == "recognize"
        else image_samples(args.dataset / args.split)
    )
    if args.command == "evaluate":
        counts = {}
        selected = []
        for sku, path in samples:
            counts[sku] = counts.get(sku, 0) + 1
            if counts[sku] <= args.queries_per_sku:
                selected.append((sku, path))
        samples = selected
    predictions = []
    started = perf_counter()
    for index, (expected, path) in enumerate(samples, 1):
        if sha(path) in reference_hashes:
            raise ValueError("Consulta também presente nas referências; avaliação inválida.")
        tick = perf_counter()
        evidence = reader.read(path)
        query_text = evidence_text(evidence)
        vector = encoder.encode(path)
        visual_ranked = visual.rank(vector)
        textual_ranked = textual.rank(query_text)
        fused = fuse(visual_ranked, textual_ranked, args.text_weight)
        original = visual.recognize(vector)
        predictions.append(
            {
                "expected": expected,
                "path": str(path.resolve()),
                "sha256": evidence["sha256"],
                "visual_top1": visual_ranked[0].sku,
                "text_top1": textual_ranked[0].sku if textual_ranked[0].similarity > 0 else None,
                "hybrid_top1": fused[0]["sku"],
                "candidates": fused[:5],
                "visual_accepted": original.sku,
                "visual_reason": original.reason,
                "ocr": evidence["lines"],
                "seconds": perf_counter() - tick,
                "sku": None,
                "requires_review": True,
                "reason": "uncalibrated_experiment",
            }
        )
        if index % 50 == 0:
            print(f"Consultas: {index}/{len(samples)}", flush=True)
    known = set(ref["sku"] for ref in textual.references)
    report = {
        "experimental": True,
        "automatic_acceptance": False,
        "gallery_manifest": manifest,
        "device": args.device,
        "torch": torch.__version__,
        "text_weight": args.text_weight,
        "split": args.split if args.command == "evaluate" else "external_image",
        "images": len(samples),
        "seconds": perf_counter() - started,
        "note": "Fusão heurística sem calibração; pontuações não são probabilidades.",
        "predictions": predictions,
    }
    if args.command == "evaluate":
        count = len(predictions)
        report["unknown_images"] = sum(row["expected"] not in known for row in predictions)
        report["top1_accuracy"] = {
            mode: sum(row[f"{mode}_top1"] == row["expected"] for row in predictions) / count
            for mode in ["visual", "text", "hybrid"]
        }
        report["hybrid_corrected_visual"] = sum(
            row["hybrid_top1"] == row["expected"] != row["visual_top1"] for row in predictions
        )
        report["hybrid_broke_visual"] = sum(
            row["visual_top1"] == row["expected"] != row["hybrid_top1"] for row in predictions
        )
    if args.device == "cuda":
        torch.cuda.synchronize()
        report["peak_cuda_allocated_bytes"] = torch.cuda.max_memory_allocated()
    write(args.report, report)
    summary = {
        key: value
        for key, value in report.items()
        if key not in {"predictions", "gallery_manifest"}
    }
    if args.command == "recognize":
        summary["prediction"] = predictions[0]
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
