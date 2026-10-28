"""Validate the deployed HTTPS frontend/gateway/PC flow with actual model inference."""

import argparse
import json
import time
import uuid
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="https://bixdata-caixa-demo.vercel.app")
    args = parser.parse_args()
    config = json.loads((ROOT / ".cache/mobile-bridge.json").read_text(encoding="utf-8-sig"))
    report = {"site": args.url, "simulated": True}
    with httpx.Client(base_url=args.url, timeout=100, headers={"Origin": args.url}) as client:
        assert client.get("/").status_code == 200
        assert client.get("/api/access").json() == {"authenticated": False}
        assert client.get("/api/health").status_code == 401
        assert client.post("/api/access", json={"code": "incorrect"}).status_code == 401
        access = client.post("/api/access", json={"code": config["DEMO_ACCESS_CODE"]})
        access.raise_for_status()
        assert "HttpOnly" in access.headers["set-cookie"]
        assert client.get("/api/health").raise_for_status().json()["simulated"] is True
        session = client.post("/api/sessions", json={}).raise_for_status().json()["session_id"]
        samples = client.get("/api/samples").raise_for_status().json()
        sample = next(sample for sample in samples if sample["id"] == "063_IMG_3153")
        photo = client.get(f"/api/samples/{sample['id']}/image").raise_for_status().content
        started = time.perf_counter()
        event = (
            client.post(
                "/api/events",
                data={"session_id": session, "event_id": uuid.uuid4().hex},
                files={"image": ("photo.jpg", photo, "image/jpeg")},
            )
            .raise_for_status()
            .json()
        )
        report["external_seconds"] = time.perf_counter() - started
        report["sample_id"] = sample["id"]
        report["top1"] = event["candidates"][0]["sku"]
        assert event["sku"] == "demo-nutella"
        assert event["decision"] == "review"
        assert client.get(f"/api/sessions/{session}/receipt").json()["lines"] == []
        command = {"session_id": session, "sku": event["sku"]}
        ack = (
            client.post(f"/api/events/{event['event_id']}/confirm", json=command)
            .raise_for_status()
            .json()
        )
        retry = (
            client.post(f"/api/events/{event['event_id']}/confirm", json=command)
            .raise_for_status()
            .json()
        )
        assert ack == retry and ack["status"] == "acknowledged"
        receipt = client.get(f"/api/sessions/{session}/receipt").raise_for_status().json()
        assert len(receipt["lines"]) == 1 and receipt["total_cents"] == 100
        for _ in range(2):
            client.post(f"/api/sessions/{session}/close", json={}).raise_for_status()
        assert client.get(f"/api/sessions/{session}/receipt").json()["closed"] is True
        report.update(
            anonymous_denied=True,
            ack_retry_one_line=True,
            close_retry_ok=True,
            confirmed_lines=1,
            physical_phone_camera_tested=False,
        )
    folder = ROOT / "artifacts/mobile-demo"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "http-validation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
