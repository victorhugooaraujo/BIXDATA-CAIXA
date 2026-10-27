"""Prepare reviewed user-product labels without copying photos into Git."""

import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from caixa_inteligente.demo.dataset import assign_splits, crop_box  # noqa: E402
from caixa_inteligente.demo.detection import select_foreground  # noqa: E402

# Identity labels verified visually; missing size/variant fields are deliberately not inferred.
PRODUCTS = [
    (3090, 3098, "nikito", "Vitarella Nikito chocolate", None),
    (3099, 3107, "bauducco", "Bauducco Choco Biscuit meio amargo 80 g", "80 g"),
    (3108, 3116, "oreo", "Oreo Original — embalagem fotografada", None),
    (3117, 3124, "toddy", "Toddy Original — embalagem fotografada", None),
    (3125, 3131, "bono", "Nestlé Bono chocolate — embalagem fotografada", None),
    (3132, 3136, "rexona", "Rexona Men — aerossol fotografado", None),
    (3138, 3145, "colgate", "Colgate Total Whitening — embalagem fotografada", None),
    (3146, 3151, "coca", "Coca-Cola original menos açúcar — garrafa fotografada", None),
    (3152, 3158, "nutella", "Ferrero Nutella 350 g", "350 g"),
    (3159, 3163, "laka", "Lacta Laka Oreo 80 g", "80 g"),
    (3165, 3168, "casaflor", "CasaFlor Mistérios do Oriente 1 L", "1 L"),
]


def main():
    folder = ROOT / "artifacts/demo-training"
    (folder / "scenes").mkdir(exist_ok=True)
    manifest = json.loads(
        (ROOT / "artifacts/bixdata-photos-2026-10-26/manifest.json").read_text(encoding="utf-8")
    )
    proposals = {item["id"]: item for item in json.loads((folder / "proposals.json").read_text())}
    samples, catalog = [], []
    for _start, _end, key, name, size in PRODUCTS:
        catalog.append(
            {
                "sku": f"demo-{key}",
                "name": name,
                "size": size,
                "price_cents": 100,
                "price_note": "Preço fictício uniforme; sem vínculo com o mercado.",
            }
        )
    sheet = None
    for index, item in enumerate(manifest["items"]):
        number = int(item["id"].split("_")[-1])
        product = next(product for product in PRODUCTS if product[0] <= number <= product[1])
        detection = select_foreground(proposals[item["id"]]["candidates"])
        # Thin edge of Laka bar: detector missed it. Manual annotation is for training only;
        # runtime still reports this localization failure, rather than receiving its true box.
        manual_boxes = {
            "070_IMG_3160": [0.50, 0.21, 0.60, 0.89],
            "071_IMG_3161": [0.47, 0.33, 0.61, 0.65],
            "072_IMG_3162": [0.12, 0.43, 0.88, 0.49],
            "073_IMG_3163": [0.47, 0.60, 0.60, 0.85],
        }
        if item["id"] in manual_boxes:
            detection = {"box": manual_boxes[item["id"]]}
        if detection is None:
            raise ValueError(f"Sem produto central: {item['id']}; revisão manual necessária")
        box = detection["box"]
        with Image.open(item["image"]) as source:
            scene = source.copy()
            scene.thumbnail((1600, 1600))
            scene.convert("RGB").save(folder / "scenes" / f"{item['id']}.jpg", quality=95)
            crop = crop_box(source, [v * source.size[i % 2] for i, v in enumerate(box)])
            crop.thumbnail((512, 512))
            crop.convert("RGB").save(folder / f"{item['id']}-crop.jpg", quality=95)
            thumb = crop.copy()
            thumb.thumbnail((220, 220))
        samples.append(
            {
                "id": item["id"],
                "sku": f"demo-{product[2]}",
                "sha256": item["decoded_sha256"],
                "box": box,
            }
        )
        if index % 20 == 0:
            sheet = Image.new("RGB", (1100, 1000), "white")
        position = index % 20
        x, y = position % 5 * 220, position // 5 * 250
        sheet.paste(thumb, (x, y))
        ImageDraw.Draw(sheet).text((x, y + 220), item["id"], fill="black")
        if index % 20 == 19 or index == len(manifest["items"]) - 1:
            sheet.save(folder / f"crops-review-{index // 20 + 1}.jpg")
    output = {
        "schema": 1,
        "source_zip_sha256": manifest["zip_sha256"],
        "scope": "11 physical products, same capture session; not commercial validation",
        "catalog": catalog,
        "samples": assign_splits(samples),
        "boxes": "Grounding DINO proposals, visually reviewed; not detector ground truth",
    }
    (folder / "dataset.json").write_text(
        json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(
        {
            split: sum(s["split"] == split for s in output["samples"])
            for split in ["train", "val", "test"]
        }
    )


if __name__ == "__main__":
    main()
