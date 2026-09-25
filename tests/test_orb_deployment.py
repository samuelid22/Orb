"""Public startup must not run on an unpaid or ephemeral configuration."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from prometheus.api.app import create_app
from prometheus.api.orb_deployment import validate_public_deployment


def configure_production(monkeypatch, tmp_path):
    disk = tmp_path / "orb-disk"
    disk.mkdir()
    output = disk / "results"
    credit_db = disk / "ledger" / "credits.sqlite3"
    uploads = tmp_path / "uploads"
    values = {
        "ORB_ENV": "production", "ORB_AI_LOCAL_TESTING": "0",
        "ORB_CREDITS_ENABLED": "1", "ORB_AI_PROVIDER": "gemini",
        "ORB_AI_MODEL": "gemini-test-model", "GEMINI_API_KEY": "test-only-key",
        "ORB_PUBLIC_ORIGIN": "https://orb.example", "ORB_DATA_DIR": str(disk),
        "ORB_OUTPUT_DIR": str(output), "ORB_UPLOAD_DIR": str(uploads),
        "ORB_CREDIT_DB": str(credit_db), "ORB_ARBITRUM_RPC_URL": "https://rpc.example.invalid",
        "ORB_CREDIT_RECEIVER": "0x" + "1" * 40,
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    for name in ("ORB_ENABLE_NIMIQ_PAYMENTS", "PROMETHEUS_PROVIDER", "PROMETHEUS_MODEL",
                 "PROMETHEUS_API_KEY", "PROMETHEUS_API_OUTPUT_DIR",
                 "PROMETHEUS_API_UPLOAD_DIR", "PROMETHEUS_CORS_ORIGINS"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(os.path, "ismount", lambda path: str(path) == str(disk))
    return output, uploads, credit_db


def test_production_requires_paid_access_and_attached_disk(monkeypatch, tmp_path):
    output, uploads, credit_db = configure_production(monkeypatch, tmp_path)
    validate_public_deployment(output, uploads, credit_db)
    for name, value in (("ORB_AI_LOCAL_TESTING", "1"), ("ORB_CREDITS_ENABLED", "0"),
                        ("ORB_PUBLIC_ORIGIN", "http://127.0.0.1:5174")):
        with monkeypatch.context() as change:
            change.setenv(name, value)
            with pytest.raises(RuntimeError):
                validate_public_deployment(output, uploads, credit_db)
    with monkeypatch.context() as change:
        change.setattr(os.path, "ismount", lambda _: False)
        with pytest.raises(RuntimeError, match="persistent disk"):
            validate_public_deployment(output, uploads, credit_db)
    with pytest.raises(RuntimeError, match="ORB_CREDIT_DB"):
        validate_public_deployment(output, uploads, tmp_path / "ephemeral.sqlite3")
    with monkeypatch.context() as change:
        change.setenv("PROMETHEUS_API_KEY", "test-only-legacy-value")
        with pytest.raises(RuntimeError, match="Orb-only configuration"):
            validate_public_deployment(output, uploads, credit_db)


def test_production_origin_cors_and_unpaid_ai_denial(monkeypatch, tmp_path):
    configure_production(monkeypatch, tmp_path)
    with TestClient(create_app()) as client:
        assert client.get("/api/health").json()["orb_ai_access"] == "credits"
        assert client.get("/api/orb/credits/config").json()["enabled"] is True
        allowed = client.options("/api/orb/wallet/challenge", headers={
            "Origin": "https://orb.example", "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        })
        assert allowed.status_code == 200
        assert allowed.headers["access-control-allow-origin"] == "https://orb.example"
        denied = client.options("/api/orb/wallet/challenge", headers={
            "Origin": "https://other.example", "Access-Control-Request-Method": "POST",
        })
        assert "access-control-allow-origin" not in denied.headers
        assert client.post("/api/orb/enhance", headers={"Origin": "https://orb.example"},
                           json={"prompt": "A blue planet over a quiet sea"}).status_code == 401
        assert client.post("/api/inspect", files={"file": ("a.mp4", b"x", "video/mp4")}).status_code == 404
        assert client.post("/api/uploads", files={"file": ("a.mp4", b"x", "video/mp4")}).status_code == 404
        assert client.post("/api/analyze", files={"file": ("a.mp4", b"x", "video/mp4")}).status_code == 404
