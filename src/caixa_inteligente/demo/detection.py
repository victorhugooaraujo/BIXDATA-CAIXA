"""Class-agnostic localization constrained to a single central presentation zone."""

import math


def select_foreground(candidates):
    ranked = []
    for candidate in candidates:
        box = candidate["box"]
        score = float(candidate["score"])
        if len(box) != 4 or not all(math.isfinite(v) for v in [*box, score]):
            raise ValueError("Detecção não finita.")
        left, top, right, bottom = box
        if not 0 <= left < right <= 1 or not 0 <= top < bottom <= 1:
            raise ValueError("Coordenadas normalizadas inválidas.")
        area = (right - left) * (bottom - top)
        cx, cy = (left + right) / 2, (top + bottom) / 2
        if not (0.015 < area < 0.9 and left <= 0.5 <= right and top <= 0.55 <= bottom):
            continue
        priority = score - 2.5 * ((cx - 0.5) ** 2 + (cy - 0.55) ** 2)
        ranked.append((priority, candidate))
    return max(ranked, key=lambda row: row[0])[1] if ranked else None


class PackageDetector:
    def __init__(self, model_id, revision, device="cuda"):
        from transformers import AutoModelForZeroShotObjectDetection, AutoProcessor

        self.processor = AutoProcessor.from_pretrained(model_id, revision=revision)
        self.model = (
            AutoModelForZeroShotObjectDetection.from_pretrained(model_id, revision=revision)
            .to(device)
            .eval()
        )
        self.device = device

    def detect(self, image):
        import torch

        preview = image.copy()
        preview.thumbnail((1200, 1200))
        inputs = self.processor(
            images=preview,
            text="a product package. a bottle. a jar. a box.",
            return_tensors="pt",
        ).to(self.device)
        with torch.inference_mode():
            outputs = self.model(**inputs)
        result = self.processor.post_process_grounded_object_detection(
            outputs,
            inputs.input_ids,
            threshold=0.23,
            text_threshold=0.2,
            target_sizes=[preview.size[::-1]],
        )[0]
        candidates = []
        for box, score in zip(
            result["boxes"].cpu().tolist(), result["scores"].cpu().tolist(), strict=True
        ):
            normalized = [
                min(1.0, max(0.0, value / preview.size[i % 2])) for i, value in enumerate(box)
            ]
            if normalized[2] > normalized[0] and normalized[3] > normalized[1]:
                candidates.append({"box": normalized, "score": score})
        return select_foreground(candidates)
