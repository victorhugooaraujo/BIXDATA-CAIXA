"""Localized product recognition with trained visual head and optional OCR evidence."""

import base64
import io
import logging
import tempfile
import time
from pathlib import Path

from PIL import Image, ImageOps

from caixa_inteligente.demo.dataset import crop_box

LOGGER = logging.getLogger(__name__)


class DemoRecognizer:
    def __init__(self, head, encoder, detector, catalog, reader=None):
        self.head, self.encoder, self.detector = head, encoder, detector
        self.catalog = {item["sku"]: item for item in catalog}
        self.reader = reader

    def __call__(self, path):
        started = time.perf_counter()
        with Image.open(path) as source:
            image = ImageOps.exif_transpose(source).convert("RGB")
        detection = self.detector.detect(image)
        if detection is None:
            return {
                "sku": None,
                "candidates": [],
                "reason": "reposition",
                "box": None,
                "automatic_acceptance": False,
                "seconds": time.perf_counter() - started,
            }
        box = detection["box"]
        crop = crop_box(image, [v * image.size[i % 2] for i, v in enumerate(box)])
        crop.thumbnail((1200, 1200))
        with tempfile.TemporaryDirectory(prefix="caixa-crop-") as directory:
            cropped_path = Path(directory) / "product.jpg"
            crop.save(cropped_path, quality=95)
            ranked = self.head.rank(self.encoder.encode(cropped_path))
            text, ocr_status = [], "disabled"
            if self.reader is not None:
                try:
                    evidence = self.reader.read(cropped_path)
                    text = [line["text"] for line in evidence["lines"] if line["score"] >= 0.7]
                    ocr_status = "ok"
                except (RuntimeError, OSError, ValueError):
                    LOGGER.exception("OCR indisponível; resultado visual continua exigindo revisão")
                    ocr_status = "unavailable"
        candidates = [{**row, "name": self.catalog[row["sku"]]["name"]} for row in ranked[:5]]
        best = candidates[0]
        # Novelty signal only; all items still require operator confirmation in the API.
        sku = best["sku"] if best["similarity"] >= 0.65 else None
        preview = crop.copy()
        preview.thumbnail((350, 350))
        buffer = io.BytesIO()
        preview.save(buffer, "JPEG")
        return {
            "sku": sku,
            "candidates": candidates,
            "reason": "review" if sku else "unknown",
            "box": box,
            "ocr": text,
            "ocr_status": ocr_status,
            "crop": "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode(),
            "automatic_acceptance": False,
            "seconds": time.perf_counter() - started,
        }
