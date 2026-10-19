"""Optional, lazy CPU OCR with content-addressed, versioned evidence caching."""

import hashlib
import json
import math
from pathlib import Path
from uuid import uuid4

import numpy as np
from PIL import Image, ImageOps

OCR_SIGNATURE = "rapidocr-3.10.0-ort-1.31.0-ppocrv4-ch-mobile-exif-rgb-v1"


class OcrReader:
    """Chinese/English/numeric baseline suitable for RPC; not a universal reader."""

    signature = OCR_SIGNATURE

    def __init__(self, cache: Path):
        self.cache = Path(cache)
        self._engine = None

    def read(self, path: Path) -> dict:
        digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()
        key = hashlib.sha256(f"{self.signature}:{digest}".encode()).hexdigest()
        destination = self.cache / f"{key}.json"
        if destination.exists():
            cached = json.loads(destination.read_text(encoding="utf-8"))
            if cached.get("signature") != self.signature or cached.get("sha256") != digest:
                raise ValueError("Cache OCR incompatível.")
            return cached
        if self._engine is None:
            try:
                from importlib.metadata import version

                from rapidocr import ModelType, OCRVersion, RapidOCR
            except ImportError as exc:
                raise RuntimeError("Execute OCR pelo ambiente isolado experiments/.") from exc
            if version("rapidocr") != "3.10.0" or version("onnxruntime") != "1.31.0":
                raise RuntimeError("Versões OCR incompatíveis; execute uv sync em experiments/.")
            self._engine = RapidOCR(
                params={
                    "Det.ocr_version": OCRVersion.PPOCRV4,
                    "Det.model_type": ModelType.MOBILE,
                    "Rec.ocr_version": OCRVersion.PPOCRV4,
                    "Rec.model_type": ModelType.MOBILE,
                    "EngineConfig.onnxruntime.intra_op_num_threads": 2,
                    "EngineConfig.onnxruntime.inter_op_num_threads": 1,
                    "Global.log_level": "warning",
                }
            )
        with Image.open(path) as source:
            image = ImageOps.exif_transpose(source).convert("RGB")
            # RapidOCR ndarray input follows OpenCV BGR convention.
            pixels = np.asarray(image)[:, :, ::-1].copy()
        output = self._engine(pixels)
        lines = []
        if output.txts is not None:
            for text, score, box in zip(output.txts, output.scores, output.boxes, strict=True):
                score = float(score)
                if not math.isfinite(score) or not 0 <= score <= 1:
                    raise ValueError("Score OCR inválido.")
                lines.append({"text": text, "score": score, "box": box.tolist()})
        result = {"signature": self.signature, "sha256": digest, "lines": lines}
        self.cache.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(f"{destination.stem}.{uuid4().hex}.tmp")
        temporary.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
        try:
            temporary.replace(destination)
        except PermissionError:
            # Windows may deny simultaneous replacement after another worker publishes.
            # Accept only a complete entry for exactly this content and configuration.
            if not destination.exists():
                raise
            published = json.loads(destination.read_text(encoding="utf-8"))
            if published.get("signature") != self.signature or published.get("sha256") != digest:
                raise ValueError("Publicação concorrente de cache incompatível.") from None
            temporary.unlink(missing_ok=True)
            return published
        return result


def evidence_text(evidence: dict, min_confidence: float = 0.7) -> str:
    return " ".join(line["text"] for line in evidence["lines"] if line["score"] >= min_confidence)
