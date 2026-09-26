"""Orb-only Arbitrum Sepolia wallet authentication and credit ledger.

Native testnet ETH is transferred to a configured, dedicated EOA. Each quote
binds the exact value and transaction input; the server verifies both from RPC.
No signing key or payment secret is held by Orb.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests
from eth_account import Account
from eth_account.messages import encode_defunct
from eth_keys.exceptions import BadSignature
from eth_utils import is_address, to_checksum_address

from prometheus.api.orb_database import OrbDatabase


CHAIN_ID = 421614
CHAIN_HEX = hex(CHAIN_ID)
TX_RE = re.compile(r"^0x[0-9a-fA-F]{64}$")
IDEMPOTENCY_RE = re.compile(r"^[A-Za-z0-9_-]{16,128}$")
QUOTE_DATA_PREFIX = "0x4f524231"  # ASCII ORB1 + random quote id bytes


class CreditError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class CreditConfig:
    database: Path
    database_url: str = ""
    public_origin: str = ""
    rpc_url: str = ""
    receiver: str = ""
    price_wei: int = 1_000_000_000_000  # 0.000001 testnet ETH per credit
    confirmations: int = 3
    enabled: bool = False

    def __post_init__(self) -> None:
        if self.price_wei <= 0 or not 1 <= self.confirmations <= 100:
            raise ValueError("Invalid Orb testnet credit price or confirmation count.")
        if self.enabled:
            origin = urlparse(self.public_origin)
            rpc = urlparse(self.rpc_url)
            if (not origin.scheme or not origin.netloc or origin.path not in {"", "/"}
                    or origin.query or origin.fragment
                    or (origin.scheme != "https" and origin.hostname not in {"localhost", "127.0.0.1"})
                    or rpc.scheme != "https" or not rpc.netloc or not is_address(self.receiver)):
                raise ValueError("Orb credit configuration requires a trusted origin, HTTPS RPC, and receiver address.")

    @property
    def ready(self) -> bool:
        return self.enabled and bool(self.public_origin and self.rpc_url and self.receiver)


class RpcClient:
    def __init__(self, url: str):
        self.url = url

    def call(self, method: str, params: list) -> object:
        try:
            response = requests.post(self.url, json={"jsonrpc": "2.0", "id": 1,
                                                     "method": method, "params": params}, timeout=12)
            response.raise_for_status()
            body = response.json()
            if not isinstance(body, dict) or "error" in body or "result" not in body:
                raise ValueError("RPC returned an error")
            return body["result"]
        except (requests.RequestException, ValueError) as exc:
            raise CreditError("Arbitrum Sepolia RPC is unavailable. Try verification again later.", 503) from exc


class CreditService:
    def __init__(self, config: CreditConfig, rpc: RpcClient | None = None):
        self.config = config
        self.rpc = rpc or RpcClient(config.rpc_url)
        self.database = OrbDatabase(config.database, config.database_url)

    def _db(self):
        return self.database.session()

    def _lock(self) -> str:
        return " FOR UPDATE" if self.database.postgres else ""

    def _require_ready(self) -> None:
        if not self.config.ready:
            raise CreditError("Arbitrum Sepolia testnet credits are not configured.", 503)

    def challenge(self, address: str, origin: str) -> dict:
        self._require_ready()
        self._check_origin(origin)
        if not is_address(address):
            raise CreditError("Enter a valid wallet address.")
        wallet = to_checksum_address(address)
        nonce = secrets.token_hex(16)
        issued = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        expiry = datetime.fromtimestamp(time.time() + 300, timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        parsed = urlparse(self.config.public_origin)
        message = (f"{parsed.netloc} wants you to sign in with your Ethereum account:\n{wallet}\n\n"
                   "Sign in to Orb's Arbitrum Sepolia testnet demo.\n\n"
                   f"URI: {self.config.public_origin}\nVersion: 1\nChain ID: {CHAIN_ID}\n"
                   f"Nonce: {nonce}\nIssued At: {issued}\nExpiration Time: {expiry}")
        with self._db() as db:
            db.execute("INSERT INTO challenges VALUES (?, ?, ?, ?, 0)",
                       (nonce, wallet.lower(), message, int(time.time()) + 300))
        return {"nonce": nonce, "message": message, "expires_at": expiry}

    def sign_in(self, nonce: str, signature: str, origin: str) -> dict:
        self._require_ready()
        self._check_origin(origin)
        if not isinstance(nonce, str) or not isinstance(signature, str) or len(signature) > 256:
            raise CreditError("Invalid wallet signature.", 401)
        with self._db() as db:
            db.begin_write()
            row = db.execute("SELECT * FROM challenges WHERE nonce=?" + self._lock(), (nonce,)).fetchone()
            if row is None or row["used"] or row["expires"] < time.time():
                raise CreditError("Sign-in challenge expired or already used.", 401)
            try:
                signer = Account.recover_message(encode_defunct(text=row["message"]), signature=signature)
            except (ValueError, TypeError, BadSignature) as exc:
                raise CreditError("Invalid wallet signature.", 401) from exc
            if signer.lower() != row["wallet"]:
                raise CreditError("Signature does not match the requested wallet.", 401)
            db.execute("UPDATE challenges SET used=1 WHERE nonce=?", (nonce,))
            token = secrets.token_urlsafe(32)
            expires = int(time.time()) + 3600
            db.execute("INSERT INTO sessions VALUES (?, ?, ?)",
                       (hashlib.sha256(token.encode()).hexdigest(), row["wallet"], expires))
            db.execute("INSERT INTO balances(wallet) VALUES (?) ON CONFLICT DO NOTHING", (row["wallet"],))
            db.commit()
        return {"token": token, "wallet": to_checksum_address(row["wallet"]), "expires_at": expires}

    def authenticate(self, authorization: str | None) -> str:
        if not authorization or not authorization.startswith("Bearer "):
            raise CreditError("Connect and sign with your wallet first.", 401)
        token = authorization[7:]
        if not 32 <= len(token) <= 128:
            raise CreditError("Wallet session is invalid.", 401)
        with self._db() as db:
            row = db.execute("SELECT wallet, expires FROM sessions WHERE token_hash=?",
                             (hashlib.sha256(token.encode()).hexdigest(),)).fetchone()
        if row is None or row["expires"] <= time.time():
            raise CreditError("Wallet session expired. Sign again.", 401)
        return row["wallet"]

    def logout(self, authorization: str | None) -> None:
        """Revoke this signed Orb session without changing credits or wallet permissions."""
        wallet = self.authenticate(authorization)
        token_hash = hashlib.sha256(authorization[7:].encode()).hexdigest()
        with self._db() as db:
            db.execute("DELETE FROM sessions WHERE token_hash=? AND wallet=?", (token_hash, wallet))

    def _check_origin(self, origin: str | None) -> None:
        if origin != self.config.public_origin:
            raise CreditError("Wallet request origin is not trusted.", 403)

    def balance(self, wallet: str) -> dict:
        with self._db() as db:
            row = db.execute("SELECT granted, consumed, reserved FROM balances WHERE wallet=?",
                             (wallet,)).fetchone()
        granted, consumed, reserved = (row["granted"], row["consumed"], row["reserved"]) if row else (0, 0, 0)
        return {"wallet": to_checksum_address(wallet), "available": granted - consumed - reserved,
                "reserved": reserved, "consumed": consumed, "granted": granted}

    def create_quote(self, wallet: str, credits: int) -> dict:
        self._require_ready()
        if credits not in {1, 3, 5}:
            raise CreditError("Choose 1, 3, or 5 testnet credits.")
        quote_id = secrets.token_hex(16)
        tx_data = QUOTE_DATA_PREFIX + quote_id
        expires = int(time.time()) + 900
        amount = self.config.price_wei * credits
        with self._db() as db:
            db.execute("INSERT INTO quotes VALUES (?, ?, ?, ?, ?, ?, NULL)",
                       (quote_id, wallet, credits, amount, tx_data, expires))
        return {"quote_id": quote_id, "chain_id": CHAIN_ID,
                "to": to_checksum_address(self.config.receiver), "value_wei": str(amount),
                "data": tx_data, "credits": credits, "expires_at": expires}

    def verify_purchase(self, wallet: str, quote_id: str, tx_hash: str) -> dict:
        self._require_ready()
        if not isinstance(tx_hash, str) or not TX_RE.fullmatch(tx_hash):
            raise CreditError("Enter a valid transaction hash.")
        tx_hash = tx_hash.lower()
        with self._db() as db:
            quote = db.execute("SELECT * FROM quotes WHERE id=? AND wallet=?", (quote_id, wallet)).fetchone()
        if quote is None:
            raise CreditError("Payment quote was not found.", 404)
        if quote["tx_hash"]:
            if quote["tx_hash"] == tx_hash:
                return {"status": "credited", "credits": quote["credits"], "balance": self.balance(wallet)}
            raise CreditError("This quote was already paid with another transaction.", 409)
        try:
            if int(self.rpc.call("eth_chainId", []), 16) != CHAIN_ID:
                raise CreditError("RPC is connected to the wrong network.", 503)
            receipt = self.rpc.call("eth_getTransactionReceipt", [tx_hash])
            tx = self.rpc.call("eth_getTransactionByHash", [tx_hash])
            if receipt is None or tx is None:
                raise CreditError("Transaction has not been mined yet.", 409)
            if not isinstance(receipt, dict) or not isinstance(tx, dict):
                raise CreditError("RPC returned incomplete transaction details.", 503)
            block_num = int(receipt["blockNumber"], 16)
            latest = int(self.rpc.call("eth_blockNumber", []), 16)
            if latest - block_num + 1 < self.config.confirmations:
                raise CreditError("Waiting for Arbitrum Sepolia confirmations.", 409)
            block = self.rpc.call("eth_getBlockByNumber", [hex(block_num), False])
            if not isinstance(block, dict) or block.get("hash") != receipt.get("blockHash"):
                raise CreditError("Transaction block is not canonical.", 409)
            if int(block["timestamp"], 16) > quote["expires"]:
                raise CreditError("Payment arrived after this quote expired. Contact support.", 409)
            code = self.rpc.call("eth_getCode", [self.config.receiver, hex(block_num)])
            if code != "0x":
                raise CreditError("Configured receiver must be a wallet, not a contract.", 503)
            valid = (int(receipt["status"], 16) == 1
                     and receipt.get("transactionHash", "").lower() == tx_hash
                     and tx.get("hash", "").lower() == tx_hash
                     and tx.get("blockHash") == receipt.get("blockHash")
                     and tx.get("from", "").lower() == wallet
                     and receipt.get("from", "").lower() == wallet
                     and tx.get("to", "").lower() == self.config.receiver.lower()
                     and receipt.get("to", "").lower() == self.config.receiver.lower()
                     and wallet != self.config.receiver.lower()
                     and int(tx["value"], 16) == quote["amount_wei"]
                     and tx.get("input", "").lower() == quote["tx_data"].lower()
                     and (tx.get("chainId") is None or int(tx["chainId"], 16) == CHAIN_ID))
        except (KeyError, ValueError, TypeError) as exc:
            raise CreditError("RPC returned incomplete transaction details.", 503) from exc
        if not valid:
            raise CreditError("Transaction does not match this Arbitrum Sepolia quote.", 400)
        with self._db() as db:
            db.begin_write()
            current = db.execute("SELECT * FROM quotes WHERE id=? AND wallet=?" + self._lock(),
                                 (quote_id, wallet)).fetchone()
            if current is None or current["tx_hash"]:
                raise CreditError("Quote was already credited.", 409)
            inserted = db.execute("INSERT INTO purchases VALUES (?, ?, ?, ?, ?, ?) "
                                  "ON CONFLICT DO NOTHING RETURNING tx_hash",
                                  (tx_hash, quote_id, wallet, quote["credits"], block_num,
                                   int(time.time()))).fetchone()
            if inserted is None:
                raise CreditError("Transaction has already been credited.", 409)
            db.execute("UPDATE quotes SET tx_hash=? WHERE id=?", (tx_hash, quote_id))
            db.execute("INSERT INTO balances(wallet) VALUES (?) ON CONFLICT DO NOTHING", (wallet,))
            db.execute("UPDATE balances SET granted=granted+? WHERE wallet=?", (quote["credits"], wallet))
            db.commit()
        return {"status": "credited", "credits": quote["credits"], "balance": self.balance(wallet)}

    def reserve(self, wallet: str, operation: str, key: str, fingerprint: str, job_id: str) -> tuple[str, bool]:
        if not isinstance(key, str) or not IDEMPOTENCY_RE.fullmatch(key):
            raise CreditError("A valid idempotency key is required.", 400)
        with self._db() as db:
            db.begin_write()
            # Postgres locks one wallet row before reading idempotency state.
            # SQLite's BEGIN IMMEDIATE provides the corresponding write lock.
            if self.database.postgres:
                db.execute("SELECT wallet FROM balances WHERE wallet=? FOR UPDATE", (wallet,)).fetchone()
            prior = db.execute("SELECT * FROM reservations WHERE wallet=? AND idem_key=?", (wallet, key)).fetchone()
            if prior:
                if prior["operation"] != operation or prior["fingerprint"] != fingerprint:
                    raise CreditError("Idempotency key was used for different content.", 409)
                return prior["job_id"], False
            updated = db.execute("UPDATE balances SET reserved=reserved+1 WHERE wallet=? "
                                 "AND granted-consumed-reserved>=1 RETURNING wallet", (wallet,)).fetchone()
            if updated is None:
                raise CreditError("No testnet credits available. Connect your wallet and buy credits.", 402)
            now = int(time.time())
            db.execute("INSERT INTO reservations VALUES (?, ?, ?, ?, ?, 'reserved', ?, ?)",
                       (job_id, wallet, operation, key, fingerprint, now, now))
            db.commit()
        return job_id, True

    def settle(self, job_id: str, success: bool) -> None:
        with self._db() as db:
            db.begin_write()
            row = db.execute("SELECT wallet, status FROM reservations WHERE job_id=?" + self._lock(),
                             (job_id,)).fetchone()
            if row is None or row["status"] != "reserved":
                return
            db.execute("UPDATE balances SET reserved=reserved-1, consumed=consumed+? WHERE wallet=?",
                       (1 if success else 0, row["wallet"]))
            db.execute("UPDATE reservations SET status=?, updated_at=? WHERE job_id=?",
                       ("consumed" if success else "released", int(time.time()), job_id))
            db.commit()

    def paid_job(self, job_id: str):
        with self._db() as db:
            return db.execute("SELECT wallet, operation, status FROM reservations WHERE job_id=?", (job_id,)).fetchone()

    def save_result(self, job_id: str, payload: dict, run_dir: Path) -> None:
        """Persist the full deliverable result before finalizing a reserved credit."""
        if self.database.postgres:
            with self._db() as db:
                db.execute("INSERT INTO results(job_id, payload, created_at) VALUES (?, ?::jsonb, ?)",
                           (job_id, json.dumps(payload, ensure_ascii=False), int(time.time())))
            return
        destination = run_dir / "orb_result.json"
        temporary = run_dir / f".orb_result.{uuid.uuid4().hex}.tmp"
        try:
            with temporary.open("x", encoding="utf-8") as result_file:
                json.dump(payload, result_file, ensure_ascii=False)
                result_file.flush()
                os.fsync(result_file.fileno())
            os.replace(temporary, destination)
            if os.name != "nt":
                directory_fd = os.open(run_dir, os.O_RDONLY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
        finally:
            temporary.unlink(missing_ok=True)

    def result(self, job_id: str, output_root: Path) -> dict | None:
        if self.database.postgres:
            with self._db() as db:
                row = db.execute("SELECT payload FROM results WHERE job_id=?", (job_id,)).fetchone()
            if row is None:
                return None
            payload = row["payload"]
            return json.loads(payload) if isinstance(payload, str) else payload
        try:
            return json.loads((output_root / job_id / "orb_result.json").read_text(encoding="utf-8"))
        except (OSError, ValueError, UnicodeError):
            return None

    def reconcile(self, output_root: Path) -> None:
        # Only a complete, durable result consumes a reserved credit after a
        # restart. Production reads it from Postgres; local mode reads disk.
        with self._db() as db:
            rows = db.execute("SELECT job_id FROM reservations WHERE status='reserved'").fetchall()
        for row in rows:
            result = self.result(row["job_id"], output_root)
            deliverable = (isinstance(result, dict) and result.get("job_id") == row["job_id"]
                           and isinstance(result.get("prompt"), str) and bool(result["prompt"].strip()))
            self.settle(row["job_id"], deliverable)
