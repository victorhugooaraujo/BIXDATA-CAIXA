from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from caixa_inteligente.demo.api import create_app


def picture():
    stream = BytesIO()
    Image.new("RGB", (80, 100), "green").save(stream, "PNG")
    return stream.getvalue()


@pytest.fixture
def client(tmp_path):
    def infer(path):
        with Image.open(path) as image:
            assert image.size == (80, 100)
        return {"sku": "a", "candidates": [{"sku": "a", "score": 0.9}], "reason": "review"}

    app = create_app(infer, [{"sku": "a", "name": "Produto A", "price_cents": 100}], tmp_path)
    with TestClient(app) as client:
        yield client


def test_image_to_review_to_ack_to_receipt_with_retry(client):
    session = client.post("/api/sessions").json()["session_id"]
    response = client.post(
        "/api/events",
        data={"session_id": session, "event_id": "test-item"},
        files={"image": ("photo.png", picture(), "image/png")},
    )
    assert response.status_code == 200
    assert response.json()["decision"] == "review"
    assert client.get(f"/api/sessions/{session}/receipt").json()["total_cents"] == 0
    one = client.post("/api/events/test-item/confirm", json={"sku": "a", "session_id": session})
    two = client.post("/api/events/test-item/confirm", json={"sku": "a", "session_id": session})
    assert one.status_code == 200
    assert one.json() == two.json()
    assert one.json()["status"] == "acknowledged"
    receipt = client.get(f"/api/sessions/{session}/receipt").json()
    assert receipt["total_cents"] == 100
    assert len(receipt["lines"]) == 1


def test_bad_bytes_and_unknown_session_do_not_create_a_sale(client):
    session = client.post("/api/sessions").json()["session_id"]
    for content in (b"not an image", b"<script>malicious</script>"):
        result = client.post(
            "/api/events",
            data={"session_id": session, "event_id": "bad"},
            files={"image": ("x.png", content, "image/png")},
        )
        assert result.status_code == 422
    assert client.get(f"/api/sessions/{session}/receipt").json()["lines"] == []
    assert (
        client.post(
            "/api/events/missing/confirm", json={"sku": "a", "session_id": session}
        ).status_code
        == 409
    )


def test_different_session_cannot_confirm_another_event(client):
    first = client.post("/api/sessions").json()["session_id"]
    other = client.post("/api/sessions").json()["session_id"]
    client.post(
        "/api/events",
        data={"session_id": first, "event_id": "item"},
        files={"image": ("x.png", picture(), "image/png")},
    )
    assert (
        client.post("/api/events/item/confirm", json={"sku": "a", "session_id": other}).status_code
        == 409
    )


def test_local_app_rejects_cross_site_origin_and_unknown_host(client):
    assert (
        client.post("/api/sessions", headers={"Origin": "https://evil.example"}).status_code == 403
    )
    assert client.get("/api/health", headers={"Host": "evil.example"}).status_code == 400
    assert client.get("/api/health").json()["simulated"] is True


def test_retained_samples_are_allowlisted_and_no_user_paths_are_served(client):
    assert client.get("/api/samples").json() == []
    assert client.get("/api/samples/arbitrary/image").status_code == 404
    assert client.get("/api/samples/..%5C..%5C.env/image").status_code == 404


def test_upload_and_pixel_limits_apply_before_inference(client, monkeypatch):
    import caixa_inteligente.demo.api as module

    session = client.post("/api/sessions").json()["session_id"]
    monkeypatch.setattr(module, "MAX_BYTES", 10)
    result = client.post(
        "/api/events",
        data={"session_id": session, "event_id": "large"},
        files={"image": ("x.png", picture(), "image/png")},
    )
    assert result.status_code == 413
    monkeypatch.setattr(module, "MAX_BYTES", 10000)
    monkeypatch.setattr(module, "MAX_PIXELS", 100)
    result = client.post(
        "/api/events",
        data={"session_id": session, "event_id": "pixels"},
        files={"image": ("x.png", picture(), "image/png")},
    )
    assert result.status_code == 422
    assert client.get(f"/api/sessions/{session}/receipt").json()["lines"] == []
