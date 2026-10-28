import pytest
from fastapi.testclient import TestClient

from caixa_inteligente.demo.api import create_app

TOKEN = "b" * 64


@pytest.fixture
def remote(tmp_path):
    app = create_app(lambda path: {}, [], tmp_path, bridge_token=TOKEN)
    with TestClient(app) as client:
        yield client


def test_tunnel_requires_token_before_any_route_or_model_access(remote):
    assert remote.get("/api/health").status_code == 401
    assert remote.post("/api/sessions").status_code == 401
    assert remote.get("/api/health", headers={"Authorization": "Bearer wrong"}).status_code == 401
    result = remote.get("/api/health", headers={"Authorization": f"Bearer {TOKEN}"})
    assert result.status_code == 200
    assert result.json()["simulated"] is True


def test_cloudflare_host_allowed_only_in_bridge_mode_and_browser_origin_rejected(remote):
    headers = {"Host": "demo-example.trycloudflare.com", "Authorization": f"Bearer {TOKEN}"}
    assert remote.get("/api/health", headers=headers).status_code == 200
    assert remote.get("/api/health", headers={**headers, "Host": "evil.example"}).status_code == 400
    assert (
        remote.post(
            "/api/sessions", headers={**headers, "Origin": "https://evil.example"}
        ).status_code
        == 403
    )


def test_bridge_does_not_expose_docs_or_local_html(remote):
    for route in ["/", "/docs", "/openapi.json"]:
        assert remote.get(route, headers={"Authorization": f"Bearer {TOKEN}"}).status_code == 404


def test_short_remote_secret_is_rejected_before_listening(tmp_path):
    with pytest.raises(ValueError, match="32"):
        create_app(lambda path: {}, [], tmp_path, bridge_token="123")


def test_receipt_reports_closed_session_for_mobile_reload(tmp_path):
    app = create_app(lambda path: {}, [], tmp_path)
    with TestClient(app) as client:
        session = client.post("/api/sessions").json()["session_id"]
        assert client.get(f"/api/sessions/{session}/receipt").json()["closed"] is False
        client.post(f"/api/sessions/{session}/close").raise_for_status()
        assert client.get(f"/api/sessions/{session}/receipt").json()["closed"] is True


def test_repeated_close_after_lost_ack_keeps_session_closed(tmp_path):
    app = create_app(lambda path: {}, [], tmp_path)
    with TestClient(app) as client:
        session = client.post("/api/sessions").json()["session_id"]
        assert client.post(f"/api/sessions/{session}/close").status_code == 200
        assert client.post(f"/api/sessions/{session}/close").status_code == 200
        assert client.get(f"/api/sessions/{session}/receipt").json()["closed"] is True


def test_windows_utf8_bom_private_configuration_is_readable_without_gpu(tmp_path):
    import importlib.util
    from pathlib import Path

    source = Path(__file__).resolve().parents[1] / "experiments/serve_demo.py"
    spec = importlib.util.spec_from_file_location("demo_launcher", source)
    launcher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(launcher)

    config = tmp_path / "private.json"
    config.write_text('{"BRIDGE_TOKEN":"' + TOKEN + '"}', encoding="utf-8-sig")
    assert launcher.read_bridge_token(config) == TOKEN
    config.write_text('{"BRIDGE_TOKEN":"short"}', encoding="utf-8")
    with pytest.raises(ValueError, match="32"):
        launcher.read_bridge_token(config)
