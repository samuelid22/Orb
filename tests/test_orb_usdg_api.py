"""Authenticated USDG API flow using mocked RPC and AI, not real payments."""

import time
import pytest

from fastapi.testclient import TestClient

from prometheus.api.app import create_app
from tests.test_orb_usdg import usdg
from tests.test_orb_credits import sign_in, TX_HASH


@pytest.mark.parametrize("value", [None, "3000", "100000"])
def test_startup_exposes_default_or_configured_usdg_price(tmp_path, monkeypatch, value):
    monkeypatch.setenv("ORB_PAYMENT_METHODS", "native_eth,usdg")
    monkeypatch.setenv("ORB_CREDITS_ENABLED", "1")
    monkeypatch.setenv("ORB_PUBLIC_ORIGIN", "http://localhost")
    monkeypatch.setenv("ORB_ARBITRUM_RPC_URL", "https://rpc.example.invalid")
    monkeypatch.setenv("ORB_CREDIT_RECEIVER", "0x" + "33" * 20)
    monkeypatch.setenv("ORB_CREDIT_PRICE_WEI", "1234")
    if value is None:
        monkeypatch.delenv("ORB_CREDIT_PRICE_USDG_BASE_UNITS", raising=False)
    else:
        monkeypatch.setenv("ORB_CREDIT_PRICE_USDG_BASE_UNITS", value)
    app = create_app(provider="mock", output_dir=tmp_path / "output", upload_dir=tmp_path / "uploads")
    with TestClient(app) as client:
        methods = client.get("/api/orb/credits/config").json()["payment_methods"]
        assert methods["usdg"]["price_base_units"] == (value or "3000")
        assert methods["native_eth"]["price_wei"] == "1234"


@pytest.mark.parametrize("value", ["0", "-3000", "3000.0", "3e3", "invalid", "", "3_000", "+3000"])
def test_startup_rejects_malformed_usdg_price(tmp_path, monkeypatch, value):
    monkeypatch.setenv("ORB_PAYMENT_METHODS", "native_eth,usdg")
    monkeypatch.setenv("ORB_CREDIT_PRICE_USDG_BASE_UNITS", value)
    with pytest.raises(ValueError, match="positive integer"):
        create_app(provider="mock", output_dir=tmp_path / "output", upload_dir=tmp_path / "uploads")


def test_signed_usdg_purchase_and_paid_enhance(usdg, tmp_path, monkeypatch):
    service, wallet, _, rpc = usdg
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-a-credential")
    monkeypatch.setenv("ORB_AI_LOCAL_TESTING", "0")
    class AI:
        def enhance(self, prompt, output, style, detail): return "A refined blue landscape"
    _, _, session = sign_in(service, wallet)
    headers = {"Origin": "http://localhost", "Authorization": "Bearer " + session["token"]}
    app = create_app(provider="gemini", orb_credit_service=service, orb_ai_service=AI(),
                     output_dir=tmp_path / "output", upload_dir=tmp_path / "uploads")
    with TestClient(app, base_url="http://localhost") as client:
        config = client.get("/api/orb/credits/config").json()
        assert config["payment_method"] == "usdg" and "price_wei" not in config
        assert config["price_base_units"] == "3000"
        assert client.post("/api/orb/enhance", headers={"Origin": "http://localhost"},
                           json={"prompt": "blue landscape"}).status_code == 401
        assert client.post("/api/orb/enhance", headers={**headers, "X-Orb-Idempotency-Key": "a" * 32},
                           json={"prompt": "blue landscape"}).status_code == 402
        quote = client.post("/api/orb/credits/quotes", headers=headers, json={"credits": 3}).json()
        rpc.paid_usdg(quote, wallet)
        path = f"/api/orb/credits/quotes/{quote['quote_id']}/verify"
        assert client.post(path, headers=headers, json={"tx_hash": TX_HASH}).json()["balance"]["available"] == 3
        assert client.post(path, headers=headers, json={"tx_hash": TX_HASH}).json()["balance"]["available"] == 3
        operation_headers = {**headers, "X-Orb-Idempotency-Key": "b" * 32}
        accepted = client.post("/api/orb/enhance", headers=operation_headers, json={"prompt": "blue landscape"})
        assert accepted.status_code == 202
        job = accepted.json()["job_id"]
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            status = client.get(f"/api/jobs/{job}", headers=headers).json()
            if status["state"] != "processing": break
            time.sleep(.05)
        assert status["state"] == "complete"
        assert client.get(f"/api/jobs/{job}/result", headers=headers).json()["prompt"] == "A refined blue landscape"
        duplicate = client.post("/api/orb/enhance", headers=operation_headers, json={"prompt": "blue landscape"})
        assert duplicate.json()["job_id"] == job
        assert client.get("/api/orb/credits/balance", headers=headers).json()["available"] == 2
