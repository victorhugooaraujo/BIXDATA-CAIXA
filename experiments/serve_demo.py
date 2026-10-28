"""Start local-only assisted checkout using trained artifacts; no PDV credentials required."""

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def build_app(folder, device="cuda", ocr=True, *, bridge_token=None):
    from PIL import Image

    from caixa_inteligente.demo.api import create_app
    from caixa_inteligente.demo.classifier import ProductClassifier
    from caixa_inteligente.demo.detection import PackageDetector
    from caixa_inteligente.demo.runtime import DemoRecognizer
    from caixa_inteligente.ocr import OcrReader
    from caixa_inteligente.vision import DINOV2_SIGNATURE, DinoV2Encoder

    detector_source = json.loads((ROOT / "configs/demo-detector.json").read_text())
    catalog = json.loads((folder / "catalog.json").read_text(encoding="utf-8"))
    head = ProductClassifier.load(folder / "classifier.npz", signature=DINOV2_SIGNATURE)
    detector = PackageDetector(detector_source["model"], detector_source["revision"], device)
    encoder = DinoV2Encoder(device)
    encoder._load_model()
    reader = OcrReader(folder / "ocr-cache") if ocr else None
    infer = DemoRecognizer(head, encoder, detector, catalog, reader)
    # Samples are full scenes from held-out test, never prepared training crops.
    names = {p["sku"]: p["name"] for p in catalog}
    dataset = json.loads((folder / "dataset.json").read_text(encoding="utf-8"))
    sample_folder = folder / "sample-previews"
    sample_folder.mkdir(exist_ok=True)
    samples = []
    for sample in dataset["samples"]:
        if sample["split"] != "test":
            continue
        preview = sample_folder / f"{sample['id']}.jpg"
        if not preview.exists():
            with Image.open(folder / "scenes" / f"{sample['id']}.jpg") as image:
                image.thumbnail((1600, 1600))
                image.convert("RGB").save(preview, quality=95)
        samples.append({"id": sample["id"], "path": str(preview), "name": names[sample["sku"]]})
    return create_app(infer, catalog, folder / "state", samples, bridge_token=bridge_token), infer


def main():
    import torch
    import uvicorn
    from pillow_heif import register_heif_opener

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--device", default="cuda", choices=["cuda", "cpu"])
    parser.add_argument("--no-ocr", action="store_true")
    parser.add_argument("--bridge-config", type=Path, help="Configuração privada da ponte móvel")
    args = parser.parse_args()
    torch.set_num_threads(4)
    register_heif_opener()
    source = Path(os.environ.get("CAIXA_DATA_ROOT", ROOT))
    os.environ.setdefault("TORCH_HOME", str(source / ".cache/torch"))
    token = None
    if args.bridge_config:
        token = json.loads(args.bridge_config.read_text(encoding="utf-8"))["BRIDGE_TOKEN"]
        if not isinstance(token, str) or len(token) < 32:
            raise ValueError("Token da ponte deve ter ao menos 32 caracteres.")
    app, _ = build_app(
        ROOT / "artifacts/demo-training", args.device, not args.no_ocr, bridge_token=token
    )
    uvicorn.run(app, host="127.0.0.1", port=args.port, access_log=False)


if __name__ == "__main__":
    main()
