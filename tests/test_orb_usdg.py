"""USDG tests use disposable wallets, temporary SQLite, and mocked chain RPC.

The Postgres bootstrap test records SQL; no external database or funds are used.
"""

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest
from eth_account import Account

from prometheus.api.orb_credits import CreditConfig, CreditError, CreditService
from prometheus.api.orb_database import OrbDatabase
from prometheus.api.orb_usdg import USDG_CONTRACT, TRANSFER_TOPIC, transfer_data
from tests.test_orb_credits import FakeRpc, TX_HASH, BLOCK_HASH, sign_in
from tests.test_orb_postgres import RecordingConnection, FakeCursor, SqliteBackedPostgresDouble


class UsdgRpc(FakeRpc):
    def call(self, method, params):
        if method == "eth_getCode" and params[0].lower() == USDG_CONTRACT.lower():
            return "0x6000"
        if method == "eth_call":
            return "0x" + f"{6:064x}"
        return super().call(method, params)

    def paid_usdg(self, quote, wallet):
        self.paid(quote, wallet, quote["token_contract"])
        self.block["timestamp"] = hex(quote["created_at"])
        self.receipt["blockNumber"] = hex(quote["created_block"] + 1)
        self.latest = hex(quote["created_block"] + 3)
        self.tx["value"] = "0x0"
        self.receipt["logs"] = [{
            "address": quote["token_contract"], "topics": [TRANSFER_TOPIC,
                "0x" + wallet.address[2:].lower().rjust(64, "0"),
                "0x" + quote["receiver"][2:].lower().rjust(64, "0")],
            "data": "0x" + f"{int(quote['amount_base_units']):064x}",
            "removed": False, "transactionHash": TX_HASH, "blockHash": BLOCK_HASH,
        }]


@pytest.fixture
def usdg(tmp_path):
    wallet = Account.create()
    receiver = Account.create().address
    config = CreditConfig(database=tmp_path / "usdg.sqlite3", public_origin="http://localhost",
                          receiver=receiver, rpc_url="https://rpc.example.invalid", enabled=True,
                          payment_method="usdg", deployment_target="usdg-staging")
    rpc = UsdgRpc()
    service = CreditService(config, rpc)
    quote = service.create_quote(wallet.address.lower(), 3)
    rpc.paid_usdg(quote, wallet)
    return service, wallet, quote, rpc


def verify(state):
    service, wallet, quote, _ = state
    return service.verify_purchase(wallet.address.lower(), quote["quote_id"], TX_HASH)


def test_exact_quote_and_valid_payment_retry_restart(usdg):
    service, wallet, quote, rpc = usdg
    assert quote["amount_base_units"] == "300000"
    assert quote["value_wei"] == "0"
    assert quote["token_symbol"] == "USDG" and quote["token_decimals"] == 6
    assert quote["chain_id"] == 421614 and quote["status"] == "pending"
    assert quote["expires_at"] - quote["created_at"] == 900
    assert quote["data"] == transfer_data(service.config.receiver, 300000)
    assert verify(usdg)["balance"]["available"] == 3
    assert verify(usdg)["balance"]["granted"] == 3
    restarted = CreditService(service.config, rpc)
    assert restarted.verify_purchase(wallet.address.lower(), quote["quote_id"], TX_HASH)["balance"]["available"] == 3
    one = service.create_quote(wallet.address.lower(), 1)
    assert one["amount_base_units"] == "100000"


@pytest.mark.parametrize("fault", [
    "target", "log_contract", "sender", "log_sender", "receiver", "amount", "failed", "missing",
    "short_data", "short_topic", "non_hex", "topic_count", "topic_zero_type", "padding", "removed",
    "log_tx", "log_block", "duplicate_log", "calldata", "native_value", "chain", "tx_chain",
    "confirmations", "canonical", "predates", "receiver_contract", "decimals", "token_no_code",
])
def test_reject_invalid_payment_without_credit(usdg, fault):
    service, wallet, quote, rpc = usdg
    log = rpc.receipt["logs"][0]
    other = "0x" + "33" * 20
    if fault == "target": rpc.tx["to"] = other
    elif fault == "log_contract": log["address"] = other
    elif fault == "sender": rpc.tx["from"] = other
    elif fault == "log_sender": log["topics"][1] = "0x" + other[2:].rjust(64, "0")
    elif fault == "receiver": log["topics"][2] = "0x" + other[2:].rjust(64, "0")
    elif fault == "amount": log["data"] = "0x" + f"{299999:064x}"
    elif fault == "failed": rpc.receipt["status"] = "0x0"
    elif fault == "missing": rpc.receipt["logs"] = []
    elif fault == "short_data": log["data"] = "0x01"
    elif fault == "short_topic": log["topics"][1] = "0x00"
    elif fault == "non_hex": log["data"] = "0x" + "z" * 64
    elif fault == "topic_count": log["topics"].append("0x" + "0" * 64)
    elif fault == "topic_zero_type": log["topics"][0] = None
    elif fault == "padding": log["topics"][1] = "0x11" + log["topics"][1][4:]
    elif fault == "removed": log["removed"] = True
    elif fault == "log_tx": log["transactionHash"] = "0x" + "11" * 32
    elif fault == "log_block": log["blockHash"] = "0x" + "11" * 32
    elif fault == "duplicate_log": rpc.receipt["logs"].append(log.copy())
    elif fault == "calldata": rpc.tx["input"] = "0x"
    elif fault == "native_value": rpc.tx["value"] = "0x1"
    elif fault == "chain": rpc.chain = "0x1"
    elif fault == "tx_chain": rpc.tx["chainId"] = "0x1"
    elif fault == "confirmations": rpc.latest = rpc.receipt["blockNumber"]
    elif fault == "canonical": rpc.block["hash"] = "0xwrong"
    elif fault == "predates": rpc.receipt["blockNumber"] = hex(quote["created_block"])
    elif fault == "receiver_contract": rpc.code = "0x6000"
    else:
        ordinary = rpc.call
        def changed(method, params):
            if fault == "decimals" and method == "eth_call": return "0x12"
            if fault == "token_no_code" and method == "eth_getCode" and params[0].lower() == USDG_CONTRACT.lower(): return "0x"
            return ordinary(method, params)
        rpc.call = changed
    with pytest.raises(CreditError): verify(usdg)
    assert service.balance(wallet.address.lower())["granted"] == 0
    with service._db() as db:
        assert db.execute("SELECT * FROM purchases").fetchone() is None


def test_expired_or_foreign_quote_and_reused_transaction(usdg):
    service, wallet, quote, rpc = usdg
    with pytest.raises(CreditError, match="not found"):
        service.verify_purchase(Account.create().address.lower(), quote["quote_id"], TX_HASH)
    verify(usdg)
    with pytest.raises(CreditError, match="already paid"):
        service.verify_purchase(wallet.address.lower(), quote["quote_id"], "0x" + "12" * 32)
    second = service.create_quote(wallet.address.lower(), 3)
    rpc.block["timestamp"] = hex(second["created_at"])
    rpc.receipt["blockNumber"] = hex(second["created_block"] + 1)
    rpc.latest = hex(second["created_block"] + 3)
    with pytest.raises(CreditError, match="already been credited"):
        service.verify_purchase(wallet.address.lower(), second["quote_id"], TX_HASH)
    with service._db() as db:
        db.execute("UPDATE quotes SET expires=0 WHERE id=?", (second["quote_id"],))
    with pytest.raises(CreditError, match="expired"):
        service.verify_purchase(wallet.address.lower(), second["quote_id"], "0x" + "13" * 32)
    assert service.balance(wallet.address.lower())["granted"] == 3


def test_concurrent_verification_grants_once(usdg):
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: verify(usdg), range(4)))
    assert all(result["status"] == "credited" for result in results)
    assert usdg[0].balance(usdg[1].address.lower())["granted"] == 3


def test_credit_grant_rolls_back_on_database_failure(usdg):
    service, wallet, quote, _ = usdg
    with service._db() as db:
        db.execute("CREATE TRIGGER fail_grant BEFORE UPDATE OF granted ON balances BEGIN SELECT RAISE(ABORT, 'test rollback'); END")
    with pytest.raises(sqlite3.IntegrityError): verify(usdg)
    with service._db() as db:
        assert db.execute("SELECT * FROM purchases").fetchone() is None
        assert db.execute("SELECT tx_hash FROM quotes WHERE id=?", (quote["quote_id"],)).fetchone()["tx_hash"] is None
        db.execute("DROP TRIGGER fail_grant")
    assert verify(usdg)["balance"]["granted"] == 3


def test_usdg_credits_use_existing_reservation_and_failure_release(usdg, tmp_path):
    service, wallet, _, rpc = usdg
    verify(usdg)
    address = wallet.address.lower()
    assert service.reserve(address, "decode", "a" * 32, "image", "job") == ("job", True)
    assert service.reserve(address, "decode", "a" * 32, "image", "duplicate") == ("job", False)
    service.settle("job", False)
    assert service.balance(address)["available"] == 3
    service.reserve(address, "enhance", "b" * 32, "text", "complete")
    folder = tmp_path / "complete"
    folder.mkdir()
    service.save_result("complete", {"job_id": "complete", "prompt": "A durable prompt"}, folder)
    restarted = CreditService(service.config, rpc)
    restarted.reconcile(tmp_path)
    assert restarted.balance(address)["consumed"] == 1
    assert restarted.balance(address)["available"] == 2


@pytest.mark.parametrize("change", [
    {"chain_id": 1}, {"payment_method": "unknown"}, {"usdg_contract": "0x" + "11" * 20},
    {"usdg_decimals": 18}, {"usdg_price": 99999}, {"deployment_target": ""},
    {"public_origin": "https://orb-azure-ten.vercel.app"}, {"receiver": USDG_CONTRACT},
])
def test_fail_closed_configuration(usdg, change):
    with pytest.raises(ValueError): replace(usdg[0].config, **change)


def test_existing_live_ledger_cannot_be_adopted(usdg, tmp_path):
    live = CreditService(CreditConfig(database=tmp_path / "live.sqlite3"))
    with live._db() as db:
        db.execute("INSERT INTO balances(wallet) VALUES (?)", (usdg[1].address.lower(),))
    with pytest.raises(RuntimeError, match="isolated"):
        CreditService(replace(usdg[0].config, database=live.config.database))
    assert live.balance(usdg[1].address.lower())["granted"] == 0


def test_rpc_failure_never_grants(usdg, monkeypatch):
    def fail(*args): raise CreditError("Arbitrum Sepolia RPC is unavailable.", 503)
    monkeypatch.setattr(usdg[3], "call", fail)
    with pytest.raises(CreditError, match="RPC"): verify(usdg)
    assert usdg[0].balance(usdg[1].address.lower())["granted"] == 0


def test_usdg_postgres_extension_bootstrap_and_existing_ledger_rejection():
    class Connection(RecordingConnection):
        def __init__(self, occupied=False):
            super().__init__()
            self.occupied = occupied
        def execute(self, sql, parameters=()):
            if sql.startswith("SELECT 1 FROM orb.balances"):
                self.calls.append((sql, parameters))
                return FakeCursor(row={"wallet": "existing"} if self.occupied else None)
            return super().execute(sql, parameters)
    clean = Connection()
    OrbDatabase._initialize_usdg(clean, True)
    assert any("CREATE TABLE orb.usdg_quotes" in sql for sql, _ in clean.calls)
    assert not any("ALTER TABLE" in sql or "DROP" in sql for sql, _ in clean.calls)
    dirty = Connection(occupied=True)
    with pytest.raises(RuntimeError, match="isolated"):
        OrbDatabase._initialize_usdg(dirty, True)
    assert not any("CREATE TABLE" in sql for sql, _ in dirty.calls)


def test_mocked_postgres_usdg_purchase_and_durable_recovery(usdg, tmp_path):
    service, wallet, _, rpc = usdg
    service.database = SqliteBackedPostgresDouble(service.database)
    assert verify(usdg)["balance"]["available"] == 3
    address = wallet.address.lower()
    service.reserve(address, "compose", "c" * 32, "reference", "durable")
    payload = {"job_id": "durable", "prompt": "A composed reference prompt"}
    service.save_result("durable", payload, tmp_path / "absent")
    restarted = CreditService(service.config, rpc)
    restarted.database = SqliteBackedPostgresDouble(restarted.database)
    restarted.reconcile(tmp_path / "absent")
    assert restarted.result("durable", tmp_path / "absent") == payload
    assert restarted.balance(address)["consumed"] == 1
    assert restarted.balance(address)["available"] == 2
