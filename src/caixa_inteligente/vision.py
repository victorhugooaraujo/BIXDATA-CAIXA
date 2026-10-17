"""Frozen DINOv2 embeddings and a small, conservative product gallery.

Recognition scores are cosine similarities, not calibrated probabilities.
The first encoder call may download the pinned upstream code and model weights.
Importing this module, constructing an encoder and loading a gallery do not.
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Protocol

import numpy as np

DINOV2_REVISION = "7764ea0f912e53c92e82eb78a2a1631e92725fc8"
DINOV2_MODEL = "dinov2_vits14"
DINOV2_MODEL_IDENTIFIER = f"facebookresearch/dinov2:{DINOV2_REVISION}:{DINOV2_MODEL}"
PREPROCESSING_SCHEMA = "exif-rgb-resize-short256-bicubic-center224-imagenet-v1"
DINOV2_SIGNATURE = json.dumps(
    {"model": DINOV2_MODEL_IDENTIFIER, "preprocessing": PREPROCESSING_SCHEMA},
    sort_keys=True,
    separators=(",", ":"),
)
GALLERY_SCHEMA_VERSION = 1


class ImageEncoder(Protocol):
    @property
    def signature(self) -> str: ...

    def encode(self, path: Path) -> np.ndarray: ...


def _signature_details(signature: str) -> dict[str, str]:
    try:
        details = json.loads(signature)
    except (TypeError, ValueError) as exc:
        raise ValueError("Encoder signature must be JSON with model and preprocessing.") from exc
    if not isinstance(details, dict) or set(details) != {"model", "preprocessing"}:
        raise ValueError("Encoder signature must contain model and preprocessing.")
    if any(not isinstance(value, str) or not value.strip() for value in details.values()):
        raise ValueError("Encoder signature fields must be nonempty strings.")
    return details


def _unit_vector(vector: np.ndarray, *, dimension: int | None = None) -> np.ndarray:
    array = np.asarray(vector)
    if array.ndim != 1 or array.size == 0 or array.dtype.kind not in "fiu":
        raise ValueError("An embedding must be a nonempty, one-dimensional numeric vector.")
    if dimension is not None and array.size != dimension:
        raise ValueError(
            f"Embedding dimension {array.size} does not match gallery dimension {dimension}."
        )
    array = array.astype(np.float64)
    if not np.isfinite(array).all():
        raise ValueError("Embeddings must contain only finite values.")
    # Scaling first avoids overflow when normalizing large, otherwise valid inputs.
    scale = np.max(np.abs(array))
    if scale == 0:
        raise ValueError("Embeddings must have a nonzero norm.")
    array /= scale
    array /= np.linalg.norm(array)
    return np.ascontiguousarray(array, dtype=np.float32)


def _preprocess_image(path: Path):
    """Return a 3x224x224 float tensor, without importing torchvision."""
    import torch
    from PIL import Image, ImageOps

    with Image.open(path) as source:
        image = ImageOps.exif_transpose(source).convert("RGB")
        width, height = image.size
        if width <= height:
            resized = (256, int(height * 256 / width))
        else:
            resized = (int(width * 256 / height), 256)
        image = image.resize(resized, Image.Resampling.BICUBIC)
        left = round((resized[0] - 224) / 2)
        top = round((resized[1] - 224) / 2)
        image = image.crop((left, top, left + 224, top + 224))
        pixels = np.asarray(image, dtype=np.float32) / 255.0

    tensor = torch.from_numpy(pixels).permute(2, 0, 1)
    mean = torch.tensor([0.485, 0.456, 0.406], dtype=torch.float32)[:, None, None]
    std = torch.tensor([0.229, 0.224, 0.225], dtype=torch.float32)[:, None, None]
    return ((tensor - mean) / std).contiguous()


class DinoV2Encoder:
    """Load a frozen ViT-S/14 lazily; use eager execution and CPU by default."""

    def __init__(self, device: str = "cpu") -> None:
        if not isinstance(device, str) or not device.strip():
            raise ValueError("Device must be a nonempty torch device string.")
        self.device = device
        self._model = None
        self._model_lock = Lock()

    @property
    def signature(self) -> str:
        return DINOV2_SIGNATURE

    def _load_model(self):
        import torch

        with self._model_lock:
            if self._model is None:
                os.environ.setdefault("XFORMERS_DISABLED", "1")
                model = torch.hub.load(
                    f"facebookresearch/dinov2:{DINOV2_REVISION}",
                    DINOV2_MODEL,
                    pretrained=True,
                    trust_repo=True,
                    skip_validation=True,
                )
                model.eval()
                model.requires_grad_(False)
                self._model = model.to(self.device)
        return self._model

    def encode(self, path: Path) -> np.ndarray:
        import torch

        # Validate/read the input before a potentially expensive model download.
        tensor = _preprocess_image(Path(path)).unsqueeze(0).to(self.device)
        model = self._load_model()
        with torch.inference_mode():
            features = model(tensor)
        if tuple(features.shape) != (1, 384):
            raise ValueError(f"Unexpected DINOv2 embedding shape: {tuple(features.shape)}.")
        return _unit_vector(features.detach().float().cpu().numpy()[0], dimension=384)


@dataclass(frozen=True, slots=True)
class Candidate:
    sku: str
    similarity: float


@dataclass(frozen=True, slots=True)
class RecognitionResult:
    sku: str | None
    similarity: float
    margin: float
    reason: str
    candidates: list[Candidate]


class Gallery:
    """Reference embeddings, scored by maximum cosine similarity per SKU.

    A result is accepted only with two or more distinct SKUs, sufficient
    similarity, and sufficient separation from the second-best SKU. Rejected
    results always have sku=None; candidates remain available for manual review.
    """

    def __init__(self, skus: list[str], embeddings: np.ndarray, signature: str) -> None:
        _signature_details(signature)
        matrix = np.asarray(embeddings)
        if matrix.ndim != 2 or matrix.shape[0] == 0 or matrix.shape[1] == 0:
            raise ValueError("A gallery requires a nonempty two-dimensional embedding matrix.")
        if len(skus) != matrix.shape[0]:
            raise ValueError("The number of SKUs must match the number of embeddings.")
        if any(not isinstance(sku, str) or not sku.strip() or sku != sku.strip() for sku in skus):
            raise ValueError("SKUs must be nonempty strings without surrounding whitespace.")
        self._embeddings = np.stack([_unit_vector(row) for row in matrix])
        self._embeddings.setflags(write=False)
        self._skus = tuple(skus)
        self._signature = signature

    @property
    def signature(self) -> str:
        return self._signature

    @property
    def sample_count(self) -> int:
        return len(self._skus)

    @property
    def class_count(self) -> int:
        return len(set(self._skus))

    @classmethod
    def build(cls, samples: list[tuple[str, Path]], encoder: ImageEncoder) -> Gallery:
        if not samples:
            raise ValueError("At least one reference image is required to build a gallery.")
        _signature_details(encoder.signature)
        skus = [sku for sku, _ in samples]
        if any(not isinstance(sku, str) or not sku.strip() or sku != sku.strip() for sku in skus):
            raise ValueError("SKUs must be nonempty strings without surrounding whitespace.")
        vectors = [_unit_vector(encoder.encode(Path(path))) for _, path in samples]
        if len({vector.size for vector in vectors}) != 1:
            raise ValueError("All reference embeddings must have the same dimension.")
        return cls(skus, np.stack(vectors), encoder.signature)

    def save(self, path: Path) -> None:
        details = _signature_details(self.signature)
        metadata = {
            "schema_version": GALLERY_SCHEMA_VERSION,
            "encoder_signature": self.signature,
            "model_identifier": details["model"],
            "preprocessing_schema": details["preprocessing"],
            "embedding_dimension": self._embeddings.shape[1],
            "sample_count": self.sample_count,
        }
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as stream:
            np.savez_compressed(
                stream,
                embeddings=self._embeddings,
                skus=np.asarray(self._skus, dtype=np.str_),
                metadata=np.asarray(json.dumps(metadata, sort_keys=True)),
            )

    @classmethod
    def load(cls, path: Path, *, expected_signature: str = DINOV2_SIGNATURE) -> Gallery:
        _signature_details(expected_signature)
        with np.load(Path(path), allow_pickle=False) as archive:
            if set(archive.files) != {"embeddings", "skus", "metadata"}:
                raise ValueError("Invalid gallery archive fields.")
            raw_metadata = archive["metadata"]
            if raw_metadata.ndim != 0 or raw_metadata.dtype.kind != "U":
                raise ValueError("Gallery metadata must be a JSON string.")
            try:
                metadata = json.loads(str(raw_metadata.item()))
            except ValueError as exc:
                raise ValueError("Invalid gallery metadata JSON.") from exc
            if (
                not isinstance(metadata, dict)
                or metadata.get("schema_version") != GALLERY_SCHEMA_VERSION
            ):
                raise ValueError("Unsupported gallery schema version; rebuild the gallery.")
            signature = metadata.get("encoder_signature")
            details = _signature_details(signature)
            if signature != expected_signature:
                raise ValueError(
                    "Gallery encoder or preprocessing is incompatible; rebuild the gallery."
                )
            if (
                metadata.get("model_identifier") != details["model"]
                or metadata.get("preprocessing_schema") != details["preprocessing"]
            ):
                raise ValueError("Gallery model/preprocessing metadata is inconsistent.")
            labels = archive["skus"]
            embeddings = archive["embeddings"]
            if labels.ndim != 1 or labels.dtype.kind != "U":
                raise ValueError("Gallery SKUs must be a one-dimensional string array.")
            gallery = cls(labels.tolist(), embeddings, signature)
            if (
                metadata.get("embedding_dimension") != gallery._embeddings.shape[1]
                or metadata.get("sample_count") != gallery.sample_count
            ):
                raise ValueError("Gallery dimensions do not match its metadata.")
            return gallery

    def recognize(
        self, vector: np.ndarray, min_similarity: float = 0.75, min_margin: float = 0.05
    ) -> RecognitionResult:
        if not math.isfinite(min_similarity) or not -1 <= min_similarity <= 1:
            raise ValueError("min_similarity must be finite and between -1 and 1.")
        if not math.isfinite(min_margin) or not 0 <= min_margin <= 2:
            raise ValueError("min_margin must be finite and between 0 and 2.")
        query = _unit_vector(vector, dimension=self._embeddings.shape[1])
        similarities = np.clip(self._embeddings @ query, -1.0, 1.0)
        by_sku: dict[str, float] = {}
        for sku, similarity in zip(self._skus, similarities, strict=True):
            by_sku[sku] = max(by_sku.get(sku, -1.0), float(similarity))
        ranked = sorted(by_sku.items(), key=lambda item: (-item[1], item[0]))
        candidates = [Candidate(sku, score) for sku, score in ranked[:3]]
        top_sku, best = ranked[0]
        margin = best - ranked[1][1] if len(ranked) > 1 else 0.0
        if len(ranked) == 1:
            reason = "single_class"
        elif best < min_similarity:
            reason = "below_similarity"
        elif margin < min_margin:
            reason = "ambiguous"
        else:
            reason = "accepted"
        return RecognitionResult(
            sku=top_sku if reason == "accepted" else None,
            similarity=best,
            margin=margin,
            reason=reason,
            candidates=candidates,
        )
