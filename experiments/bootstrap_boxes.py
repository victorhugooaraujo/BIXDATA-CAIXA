"""Generate detector proposals for review; these are never evaluation ground truth."""

import json
from pathlib import Path

from PIL import Image, ImageDraw


def main():
    import torch
    from huggingface_hub import HfApi
    from transformers import AutoModelForZeroShotObjectDetection, AutoProcessor

    root = Path(__file__).resolve().parents[1]
    source = root / "artifacts/bixdata-photos-2026-10-26"
    target = root / "artifacts/demo-training"
    target.mkdir(parents=True, exist_ok=True)
    model_id = "IDEA-Research/grounding-dino-tiny"
    lock = target / "detector-source.json"
    if lock.exists():
        revision = json.loads(lock.read_text())["revision"]
    else:
        revision = HfApi().model_info(model_id).sha
        lock.write_text(json.dumps({"model": model_id, "revision": revision}))
    processor = AutoProcessor.from_pretrained(model_id, revision=revision)
    model = (
        AutoModelForZeroShotObjectDetection.from_pretrained(model_id, revision=revision)
        .to("cuda")
        .eval()
    )
    output = target / "proposals.json"
    records = json.loads(output.read_text()) if output.exists() else []
    done = {record["id"] for record in records}
    items = json.loads((source / "manifest.json").read_text())["items"]
    for item in items:
        if item["id"] in done:
            continue
        with Image.open(item["image"]) as original:
            image = original.convert("RGB")
            image.thumbnail((1200, 1200))
        inputs = processor(
            images=image, text="a product package. a bottle. a jar. a box.", return_tensors="pt"
        ).to("cuda")
        with torch.inference_mode():
            result = model(**inputs)
        detected = processor.post_process_grounded_object_detection(
            result,
            inputs.input_ids,
            threshold=0.23,
            text_threshold=0.2,
            target_sizes=[image.size[::-1]],
        )[0]
        boxes = detected["boxes"].cpu().tolist()
        scores = detected["scores"].cpu().tolist()
        candidates = []
        for box, score in zip(boxes, scores, strict=True):
            left, top, right, bottom = box
            area = (right - left) * (bottom - top) / (image.width * image.height)
            cx, cy = (left + right) / 2 / image.width, (top + bottom) / 2 / image.height
            if 0.015 < area < 0.95:
                priority = score - 0.6 * ((cx - 0.5) ** 2 + (cy - 0.5) ** 2)
                candidates.append((priority, box, score))
        candidates.sort(reverse=True)
        record = {
            "id": item["id"],
            "candidates": [
                {"box": [b / image.size[i % 2] for i, b in enumerate(box)], "score": score}
                for _, box, score in candidates[:6]
            ],
        }
        records.append(record)
        output.write_text(json.dumps(records, indent=2))
        if candidates:
            draw = ImageDraw.Draw(image)
            for index, (_, box, _) in enumerate(candidates[:3]):
                draw.rectangle(box, outline=["lime", "red", "blue"][index], width=4)
                draw.text(
                    (box[0], box[1]), str(index), fill="black", stroke_width=1, stroke_fill="white"
                )
        image.thumbnail((350, 350))
        image.save(target / f"{item['id']}-proposal.jpg")
        print(item["id"], len(candidates), flush=True)
    print("Proposals complete; review required", flush=True)


if __name__ == "__main__":
    main()
