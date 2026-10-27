"""Exercise real running models over HTTP; expected labels stay outside inference requests."""

import json
import time
import uuid
from pathlib import Path

import httpx
import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def main():
    folder = ROOT / "artifacts/demo-training"
    dataset = json.loads((folder / "dataset.json").read_text(encoding="utf-8"))
    expected = {s["id"]: s["sku"] for s in dataset["samples"] if s["split"] == "test"}
    results = []
    with httpx.Client(base_url="http://127.0.0.1:8765", timeout=180) as client:
        health = client.get("/api/health").raise_for_status().json()
        assert health["simulated"] and health["mode"] == "assisted"
        session = client.post("/api/sessions").raise_for_status().json()["session_id"]
        samples = client.get("/api/samples").raise_for_status().json()
        assert {s["id"] for s in samples} == set(expected)
        for sample in samples:
            raw = client.get(f"/api/samples/{sample['id']}/image").raise_for_status().content
            event = uuid.uuid4().hex
            start = time.perf_counter()
            response = (
                client.post(
                    "/api/events",
                    data={"session_id": session, "event_id": event},
                    files={"image": ("sample.jpg", raw, "image/jpeg")},
                )
                .raise_for_status()
                .json()
            )
            top = response["candidates"][0]["sku"] if response["candidates"] else None
            results.append(
                {
                    "id": sample["id"],
                    "expected": expected[sample["id"]],
                    "top1": top,
                    "sku": response["sku"],
                    "correct": top == expected[sample["id"]],
                    "reason": response["reason"],
                    "ocr_status": response.get("ocr_status"),
                    "seconds": time.perf_counter() - start,
                    "event_id": event,
                }
            )
            assert response["decision"] == "review"
            print(
                sample["id"],
                top,
                results[-1]["correct"],
                round(results[-1]["seconds"], 2),
                flush=True,
            )
        receipt = client.get(f"/api/sessions/{session}/receipt").raise_for_status().json()
        assert not receipt["lines"], "Inference must not create a receipt line"
        # Use the last item: its event is recent. Explicit correction is allowed in assisted mode.
        event = results[-1]["event_id"]
        sku = results[-1]["expected"]
        command = {"session_id": session, "sku": sku}
        first = client.post(f"/api/events/{event}/confirm", json=command).raise_for_status().json()
        retry = client.post(f"/api/events/{event}/confirm", json=command).raise_for_status().json()
        assert first == retry and first["status"] == "acknowledged"
        receipt = client.get(f"/api/sessions/{session}/receipt").raise_for_status().json()
        assert len(receipt["lines"]) == 1 and receipt["total_cents"] == 100
        client.post(f"/api/sessions/{session}/close").raise_for_status()
    report = {
        "images": len(results),
        "top1_correct": sum(r["correct"] for r in results),
        "localized": sum(r["top1"] is not None for r in results),
        "automatic_sales": 0,
        "ack_retry_one_line": True,
        "p50_seconds": float(np.quantile([r["seconds"] for r in results], 0.5)),
        "p95_seconds": float(np.quantile([r["seconds"] for r in results], 0.95)),
        "limitations": (
            "21 views from the same 11 physical products/session, not commercial validation"
        ),
        "results": results,
    }
    (folder / "http-validation.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps({k: v for k, v in report.items() if k != "results"}, indent=2), flush=True)


if __name__ == "__main__":
    main()
