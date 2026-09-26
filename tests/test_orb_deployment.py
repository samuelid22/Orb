"""Public startup must select paid access and the Postgres persistence path."""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from prometheus.api.app import create_app
from prometheus.api.orb_credits import CreditConfig, CreditService
from prometheus.api.orb_deployment import validate_public_deployment


POSTGRES_URL = "postgresql://orb:placeholder@db.example.invalid:5432/orb?sslmode=require"


def configure_production(monkeypatch, tmp_path):
    uploads = tmp_path / "uploads"
    values = {
        "ORB_ENV": "production", "ORB_AI_LOCAL_TESTING": "0",
        "ORB_CREDITS_ENABLED": "1", "ORB_AI_PROVIDER": "gemini",
        "ORB_AI_MODEL": "gemini-test-model", "GEMINI_API_KEY": "test-only-key",
        "ORB_PUBLIC_ORIGIN": "https://orb.example", "ORB_UPLOAD_DIR": str(uploads),
        "ORB_DATABASE_URL": POSTGRES_URL, "ORB_ARBITRUM_RPC_URL": "https://rpc.example.invalid",
        "ORB_CREDIT_RECEIVER": "0x" + "1" * 40,
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    for name in ("ORB_ENABLE_NIMIQ_PAYMENTS", "PROMETHEUS_PROVIDER", "PROMETHEUS_MODEL",
                 "PROMETHEUS_API_KEY", "PROMETHEUS_API_OUTPUT_DIR", "PROMETHEUS_API_UPLOAD_DIR",
                 "PROMETHEUS_CORS_ORIGINS", "ORB_DATA_DIR", "ORB_CREDIT_DB", "ORB_OUTPUT_DIR"):
        monkeypatch.delenv(name, raising=False)
    return uploads


def test_production_requires_postgres_without_disk(monkeypatch, tmp_path):
    uploads = configure_production(monkeypatch, tmp_path)
    validate_public_deployment(uploads, POSTGRES_URL)
    for name, value in (("ORB_AI_LOCAL_TESTING", "1"), ("ORB_CREDITS_ENABLED", "0"),
                        ("ORB_PUBLIC_ORIGIN", "http://127.0.0.1:5174")):
        with monkeypatch.context() as change:
            change.setenv(name, value)
            with pytest.raises(RuntimeError):
                validate_public_deployment(uploads, POSTGRES_URL)
    for database_url in ("", "sqlite:///tmp/orb.sqlite3", "postgresql://bad"):
        with pytest.raises(RuntimeError, match="Postgres"):
            validate_public_deployment(uploads, database_url)
    with monkeypatch.context() as change:
        change.setenv("PROMETHEUS_API_KEY", "test-only-legacy-value")
        with pytest.raises(RuntimeError, match="Orb-only configuration"):
            validate_public_deployment(uploads, POSTGRES_URL)


def test_production_origin_cors_and_unpaid_ai_denial_with_mock_store(monkeypatch, tmp_path):
    uploads = configure_production(monkeypatch, tmp_path)
    # A local SQLite test double exercises the HTTP guard without contacting
    # Supabase. Real Postgres connectivity is tested only when available.
    service = CreditService(CreditConfig(
        database=tmp_path / "mock-credits.sqlite3", public_origin="https://orb.example",
        rpc_url="https://rpc.example.invalid", receiver="0x" + "1" * 40, enabled=True))
    service.config = replace(service.config, database_url=POSTGRES_URL)
    local_store = service.database
    service.database = SimpleNamespace(postgres=True, session=local_store.session)
    with TestClient(create_app(output_dir=tmp_path / "scratch", upload_dir=uploads,
                               orb_credit_service=service)) as client:
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
