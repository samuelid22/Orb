"""Dual-method tests: isolated SQLite, disposable signers, mocked chain/AI."""

from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor

import pytest
from eth_account import Account
from fastapi.testclient import TestClient

from prometheus.api.app import create_app
from prometheus.api.orb_credits import CreditConfig, CreditError, CreditService
from tests.test_orb_credits import TX_HASH, sign_in
from tests.test_orb_usdg import UsdgRpc


@pytest.fixture
def dual(tmp_path):
    wallet = Account.create()
    config = CreditConfig(database=tmp_path / "dual.sqlite3", public_origin="http://localhost",
        receiver=Account.create().address, rpc_url="https://rpc.example.invalid", enabled=True,
        price_wei=1234, payment_methods=("native_eth", "usdg"))
    rpc = UsdgRpc()
    return CreditService(config, rpc), wallet, rpc


def payment(state, method, tx_hash=TX_HASH):
    service, wallet, rpc = state
    quote = service.create_quote(wallet.address.lower(), 3, method)
    if method == "usdg":
        rpc.paid_usdg(quote, wallet)
        rpc.tx["hash"] = rpc.receipt["transactionHash"] = rpc.receipt["logs"][0]["transactionHash"] = tx_hash
    else:
        rpc.paid(quote, wallet, service.config.receiver, tx_hash)
    return quote


def verify(state, quote, tx_hash=TX_HASH):
    return state[0].verify_purchase(state[1].address.lower(), quote["quote_id"], tx_hash)


@pytest.mark.parametrize("method", ["native_eth", "usdg"])
def test_quote_settlement_replay_restart_reserve_release_and_consume(dual, tmp_path, method):
    service, wallet, rpc = dual
    quote = payment(dual, method)
    assert quote["payment_method"] == method
    assert int(quote["value_wei"]) == (3702 if method == "native_eth" else 0)
    if method == "usdg": assert quote["amount_base_units"] == "9000"
    assert verify(dual, quote)["balance"]["granted"] == 3
    assert verify(dual, quote)["balance"]["granted"] == 3
    with pytest.raises(CreditError, match="already paid"):
        verify(dual, quote, "0x" + "55" * 32)
    restarted = CreditService(service.config, rpc)
    assert restarted.balance(wallet.address.lower())["available"] == 3
    restarted.reserve(wallet.address.lower(), "decode", "a" * 32, "media", "job")
    restarted.settle("job", False)
    assert restarted.balance(wallet.address.lower())["available"] == 3
    restarted.reserve(wallet.address.lower(), "enhance", "b" * 32, "text", "success")
    restarted.settle("success", True)
    assert restarted.balance(wallet.address.lower())["available"] == 2


@pytest.mark.parametrize("first,second", [("native_eth", "usdg"), ("usdg", "native_eth")])
def test_both_methods_fund_one_wallet_and_share_global_transaction_uniqueness(dual, first, second):
    eth_quote = payment(dual, first)
    verify(dual, eth_quote)
    token_quote = payment(dual, second)  # simulated RPC reuses the same hash across assets
    with pytest.raises(CreditError, match="already been credited"): verify(dual, token_quote)
    new_hash = "0x" + "56" * 32
    token_quote = payment(dual, second, new_hash)
    assert verify(dual, token_quote, new_hash)["balance"]["granted"] == 6


@pytest.mark.parametrize("quote_method,transaction_method", [("native_eth", "usdg"), ("usdg", "native_eth")])
def test_cross_method_settlement_is_rejected(dual, quote_method, transaction_method):
    quote = payment(dual, quote_method)
    payment(dual, transaction_method)
    if quote_method == "usdg":
        dual[2].receipt["blockNumber"] = hex(quote["created_block"] + 1)
        dual[2].latest = hex(quote["created_block"] + 3)
    with pytest.raises(CreditError, match="does not match"): verify(dual, quote)
    assert dual[0].balance(dual[1].address.lower())["granted"] == 0


@pytest.mark.parametrize("method", ["native_eth", "usdg"])
def test_expired_quote_and_atomic_rollback(dual, method):
    service, wallet, rpc = dual
    quote = payment(dual, method)
    with service._db() as db:
        db.execute("CREATE TRIGGER fail_grant BEFORE UPDATE OF granted ON balances BEGIN SELECT RAISE(ABORT, 'rollback'); END")
    import sqlite3
    with pytest.raises(sqlite3.IntegrityError): verify(dual, quote)
    with service._db() as db:
        assert db.execute("SELECT * FROM purchases").fetchone() is None
        assert db.execute("SELECT tx_hash FROM quotes WHERE id=?", (quote["quote_id"],)).fetchone()["tx_hash"] is None
        db.execute("DROP TRIGGER fail_grant")
        db.execute("UPDATE quotes SET expires=0 WHERE id=?", (quote["quote_id"],))
    with pytest.raises(CreditError, match="expired"): verify(dual, quote)
    assert service.balance(wallet.address.lower())["granted"] == 0


@pytest.mark.parametrize("method", ["native_eth", "usdg"])
def test_concurrent_same_quote_verification(dual, method):
    quote = payment(dual, method)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: verify(dual, quote), range(4)))
    assert all(result["status"] == "credited" for result in results)
    assert dual[0].balance(dual[1].address.lower())["granted"] == 3


def test_invalid_disabled_and_missing_method(dual):
    service, wallet, rpc = dual
    for method in (None, "native", "wrong", [], 1):
        with pytest.raises(CreditError): service.create_quote(wallet.address.lower(), 1, method)
    quote = payment(dual, "usdg")
    native = CreditService(replace(service.config, payment_methods=("native_eth",)), rpc)
    with pytest.raises(CreditError, match="not enabled"):
        native.create_quote(wallet.address.lower(), 1, "usdg")
    with pytest.raises(CreditError, match="not enabled"):
        native.verify_purchase(wallet.address.lower(), quote["quote_id"], TX_HASH)


@pytest.mark.parametrize("methods", [("native_eth", "native_eth"), ("wrong",), ("",)])
def test_bad_methods_configuration_fails_closed(dual, methods):
    with pytest.raises(ValueError): replace(dual[0].config, payment_methods=methods)


def test_api_config_and_explicit_quote_contract(dual, tmp_path, monkeypatch):
    service, wallet, _ = dual
    monkeypatch.setenv("GEMINI_API_KEY", "test-only-provider-placeholder")
    monkeypatch.setenv("ORB_AI_LOCAL_TESTING", "0")
    app = create_app(provider="gemini", output_dir=tmp_path / "output", upload_dir=tmp_path / "uploads", orb_credit_service=service)
    _, _, session = sign_in(service, wallet)
    headers = {"Origin": "http://localhost", "Authorization": "Bearer " + session["token"]}
    with TestClient(app) as client:
        config = client.get("/api/orb/credits/config").json()
        assert config["enabled"]
        assert config["payment_methods"]["native_eth"]["price_wei"] == "1234"
        assert config["payment_methods"]["usdg"]["price_base_units"] == "3000"
        assert all(config["payment_methods"][method]["enabled"] for method in ("native_eth", "usdg"))
        assert client.post("/api/orb/credits/quotes", headers=headers, json={"credits": 3}).status_code == 400
        for method in ("native_eth", "usdg"):
            result = client.post("/api/orb/credits/quotes", headers=headers, json={"credits": 3, "payment_method": method})
            assert result.status_code == 200
            assert result.json()["payment_method"] == method
        for method in ("wrong", "native", [], None):
            assert client.post("/api/orb/credits/quotes", headers=headers, json={"credits": 1, "payment_method": method}).status_code == 400
