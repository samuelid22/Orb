"""Trusted-origin security tests use disposable wallets/SQLite and mocked RPC only."""

from dataclasses import replace
from urllib.parse import urlsplit
import sqlite3

import pytest
from eth_account import Account
from eth_account.messages import encode_defunct
from fastapi.testclient import TestClient

from prometheus.api.app import create_app
from prometheus.api.orb_credits import CreditConfig, CreditError, CreditService
from prometheus.api.orb_origins import OriginError, TrustedOrigins, canonical_origin
from tests.test_orb_deployment import configure_production, POSTGRES_URL
from prometheus.api.orb_deployment import validate_public_deployment
from tests.test_orb_usdg import UsdgRpc
from tests.test_orb_credits import TX_HASH


A = "https://staging-existing.example"
B = "https://orb-fchisqse8-samuelid22.vercel.app"
X = "https://untrusted.example"


@pytest.fixture
def ledger(tmp_path):
    wallet = Account.create()
    rpc = UsdgRpc()
    config = CreditConfig(database=tmp_path / "origins.sqlite3", public_origin=A,
                          additional_public_origins=B, enabled=True,
                          receiver=Account.create().address, rpc_url="https://rpc.example.invalid",
                          payment_methods=("native_eth", "usdg"))
    return CreditService(config, rpc), wallet, rpc


def signature(wallet, challenge):
    return Account.sign_message(encode_defunct(text=challenge["message"]), wallet.key).signature.hex()


@pytest.mark.parametrize("value,expected", [
    ("HTTPS://Example.COM:443/", "https://example.com"),
    ("https://example.com:8443/", "https://example.com:8443"),
    ("http://localhost:80/", "http://localhost"),
    ("http://127.0.0.1:5174", "http://127.0.0.1:5174"),
    ("http://[::1]:5174/", "http://[::1]:5174"),
    ("https://[2001:0db8::1]:443", "https://[2001:db8::1]"),
    ("https://xn--bcher-kva.example", "https://xn--bcher-kva.example"),
])
def test_canonical_browser_origin(value, expected):
    assert canonical_origin(value) == expected


@pytest.mark.parametrize("value", [
    "", None, "null", "*", "https://*.vercel.app", "*.vercel.app",
    "https://example.com/path", "https://example.com//", "https://example.com/?x=1",
    "https://example.com?", "https://example.com/#", "https://example.com#fragment",
    "https://user:password@example.com", "https://user@example.com", "https://@example.com",
    "https://", "ftp://example.com", "javascript:example.com", "//example.com",
    "http://example.com", "https://example.com:0", "https://example.com:65536",
    "https://example.com:abc", "https://example.com:", "https://example.com:443:80",
    "https://example..com", "https://-example.com", "https://example_.com",
    "https://example.com.", "https://example.com\\evil", "https://example%2ecom",
    "https://example.com\n", " https://example.com", "https://exam ple.com",
    "https://127.1", "https://2130706433", "https://0x7f000001", "https://127.0.0.999",
    "https://[::1]evil", "https://[::1]:", "https://example.com,https://other.example",
])
def test_rejects_invalid_origins_without_echoing_values(value):
    with pytest.raises(OriginError) as exc:
        canonical_origin(value)
    assert "password" not in str(exc.value)


@pytest.mark.parametrize("additional", ["", " ", "\t"])
def test_empty_additional_origins_preserve_single_origin(additional):
    origins = TrustedOrigins.parse(A, additional)
    assert origins.primary == A and origins.origins == (A,)
    assert origins.require(A) == A
    with pytest.raises(OriginError):
        origins.require(B)


def test_additional_origin_lists_trim_and_deduplicate_canonical_origins():
    origins = TrustedOrigins.parse(f" {A}/ ", f" {B}/ , {A.upper()}:443, {B}, https://third.example:8443 ")
    assert origins.primary == A
    assert origins.origins == (A, B, "https://third.example:8443")
    assert origins.require(f"{B}:443/") == B
    assert TrustedOrigins.parse(A, B).origins == (A, B)
    assert TrustedOrigins.parse().origins == ()


@pytest.mark.parametrize("additional", [",", f"{B},", f",{B}", f"{B}, ,{X}", "*", f"{B}/path"])
def test_invalid_allowlist_is_not_silently_filtered(additional):
    with pytest.raises(OriginError):
        TrustedOrigins.parse(A, additional)
    with pytest.raises(OriginError):
        CreditConfig(database=None, public_origin=A, additional_public_origins=additional)


def test_primary_cannot_be_a_list_and_additional_requires_primary():
    with pytest.raises(OriginError):
        TrustedOrigins.parse(f"{A},{B}")
    with pytest.raises(OriginError):
        TrustedOrigins.parse("", B)
    with pytest.raises(OriginError, match="eight"):
        TrustedOrigins.parse(A, ",".join(f"https://preview{i}.example" for i in range(8)))


@pytest.mark.parametrize("origin", [A, B])
def test_challenge_and_signature_bound_to_requesting_origin(ledger, origin):
    service, wallet, _ = ledger
    challenge = service.challenge(wallet.address, origin)
    message = challenge["message"]
    assert message.startswith(f"{urlsplit(origin).netloc} wants you to sign in with your Ethereum account:\n{wallet.address}\n")
    assert f"URI: {origin}\nVersion: 1\nChain ID: 421614\nNonce: {challenge['nonce']}\n" in message
    with sqlite3.connect(service.config.database) as db:
        assert db.execute("SELECT message FROM challenges WHERE nonce=?", (challenge["nonce"],)).fetchone()[0] == message
    signed = signature(wallet, challenge)
    session = service.sign_in(challenge["nonce"], signed, origin)
    assert service.authenticate("Bearer " + session["token"]) == wallet.address.lower()
    with pytest.raises(CreditError, match="already used"):
        service.sign_in(challenge["nonce"], signed, origin)


@pytest.mark.parametrize("created,other", [(A, B), (B, A)])
def test_trusted_cross_origin_replay_rejected_without_consuming_nonce(ledger, created, other):
    service, wallet, _ = ledger
    challenge = service.challenge(wallet.address, created)
    signed = signature(wallet, challenge)
    with pytest.raises(CreditError, match="different origin") as exc:
        service.sign_in(challenge["nonce"], signed, other)
    assert exc.value.status == 403
    with sqlite3.connect(service.config.database) as db:
        assert db.execute("SELECT used FROM challenges WHERE nonce=?", (challenge["nonce"],)).fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 0
    service.sign_in(challenge["nonce"], signed, created)
    with pytest.raises(CreditError):
        service.sign_in(challenge["nonce"], signed, other)


@pytest.mark.parametrize("origin", [A, B])
def test_wallet_signature_and_challenge_expiry_still_required(ledger, origin):
    service, wallet, _ = ledger
    challenge = service.challenge(wallet.address, origin)
    with pytest.raises(CreditError, match="does not match"):
        service.sign_in(challenge["nonce"], signature(Account.create(), challenge), origin)
    with sqlite3.connect(service.config.database) as db:
        db.execute("UPDATE challenges SET expires=0 WHERE nonce=?", (challenge["nonce"],))
    with pytest.raises(CreditError, match="expired"):
        service.sign_in(challenge["nonce"], signature(wallet, challenge), origin)
    with sqlite3.connect(service.config.database) as db:
        assert db.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 0


@pytest.mark.parametrize("origin", [None, "", "null", X, A + ".evil.example", "https://*.example", A + "/path"])
def test_missing_malformed_or_untrusted_origin_rejected(ledger, origin):
    service, wallet, _ = ledger
    with pytest.raises(CreditError) as exc:
        service.challenge(wallet.address, origin)
    assert exc.value.status == 403
    challenge = service.challenge(wallet.address, A)
    with pytest.raises(CreditError) as exc:
        service.sign_in(challenge["nonce"], signature(wallet, challenge), origin)
    assert exc.value.status == 403


@pytest.mark.parametrize("tamper", ["missing_uri", "duplicate_uri", "untrusted_uri", "wrong_domain"])
def test_malformed_stored_origin_binding_fails_closed_even_with_valid_signature(ledger, tamper):
    service, wallet, _ = ledger
    challenge = service.challenge(wallet.address, A)
    message = challenge["message"]
    if tamper == "missing_uri":
        message = message.replace(f"URI: {A}\n", "")
    elif tamper == "duplicate_uri":
        message += f"\nURI: {A}"
    elif tamper == "untrusted_uri":
        message = message.replace(f"URI: {A}", f"URI: {X}")
    else:
        message = message.replace(urlsplit(A).netloc, urlsplit(B).netloc, 1)
    with sqlite3.connect(service.config.database) as db:
        db.execute("UPDATE challenges SET message=? WHERE nonce=?", (message, challenge["nonce"]))
    challenge["message"] = message
    with pytest.raises(CreditError, match="origin is invalid"):
        service.sign_in(challenge["nonce"], signature(wallet, challenge), A)


def test_single_origin_message_format_existing_challenge_and_session_survive(ledger):
    service, wallet, rpc = ledger
    previous = CreditService(replace(service.config, additional_public_origins=""), rpc)
    challenge = previous.challenge(wallet.address, A)
    lines = challenge["message"].splitlines()
    assert lines[:8] == [f"{urlsplit(A).netloc} wants you to sign in with your Ethereum account:",
                         wallet.address, "", "Sign in to Orb's Arbitrum Sepolia testnet demo.",
                         "", f"URI: {A}", "Version: 1", "Chain ID: 421614"]
    assert lines[8:] == [f"Nonce: {challenge['nonce']}", lines[9], f"Expiration Time: {challenge['expires_at']}"]
    assert lines[9].startswith("Issued At: ")
    # The same signed message generated by the single-origin service remains valid.
    session = service.sign_in(challenge["nonce"], signature(wallet, challenge), A)
    restarted = CreditService(service.config, rpc)
    assert restarted.authenticate("Bearer " + session["token"]) == wallet.address.lower()


@pytest.mark.parametrize("additional", ["", B])
def test_http_cors_and_wallet_authorization_use_same_allowlist(ledger, tmp_path, additional):
    service, wallet, rpc = ledger
    service = CreditService(replace(service.config, additional_public_origins=additional), rpc)
    app = create_app(provider="mock", output_dir=tmp_path / "output", upload_dir=tmp_path / "uploads",
                     orb_credit_service=service)
    with TestClient(app) as client:
        for origin in (A, B, X, "*", A + "/path", A.upper() + ":443/"):
            allowed = origin in (A, A.upper() + ":443/") or origin == B and bool(additional)
            preflight = client.options("/api/orb/wallet/challenge", headers={
                "Origin": origin, "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "authorization,content-type,x-orb-idempotency-key"})
            assert preflight.status_code == (200 if allowed else 400)
            assert preflight.headers.get("access-control-allow-origin") == (origin if allowed else None)
            assert "access-control-allow-credentials" not in preflight.headers
            response = client.post("/api/orb/wallet/challenge", headers={"Origin": origin},
                                   json={"address": wallet.address})
            assert response.status_code == (200 if allowed else 403)
            for path in ("/api/health", "/api/orb/credits/config"):
                response = client.get(path, headers={"Origin": origin})
                assert response.headers.get("access-control-allow-origin") == (origin if allowed else None)
        assert client.post("/api/orb/wallet/challenge", json={"address": wallet.address}).status_code == 403


@pytest.mark.parametrize("origin,other", [(A, B), (B, A)])
def test_http_cross_origin_challenge_payment_and_logout_boundaries(ledger, tmp_path, monkeypatch, origin, other):
    service, wallet, _ = ledger
    monkeypatch.setenv("GEMINI_API_KEY", "test-only-key")
    app = create_app(provider="gemini", output_dir=tmp_path / "output", upload_dir=tmp_path / "uploads",
                     orb_credit_service=service)
    with TestClient(app) as client:
        challenge = client.post("/api/orb/wallet/challenge", headers={"Origin": origin},
                                json={"address": wallet.address}).json()
        payload = {"nonce": challenge["nonce"], "signature": signature(wallet, challenge)}
        assert client.post("/api/orb/wallet/sign-in", headers={"Origin": other}, json=payload).status_code == 403
        session = client.post("/api/orb/wallet/sign-in", headers={"Origin": origin}, json=payload).json()
        headers = {"Origin": origin, "Authorization": "Bearer " + session["token"]}
        assert client.get("/api/orb/credits/balance", headers=headers).json()["available"] == 0
        for method in ("native_eth", "usdg"):
            quote = client.post("/api/orb/credits/quotes", headers=headers,
                                json={"credits": 3, "payment_method": method})
            assert quote.status_code == 200 and quote.json()["payment_method"] == method
            for rejected in (X, ""):
                assert client.post("/api/orb/credits/quotes", headers={**headers, "Origin": rejected},
                                   json={"credits": 3, "payment_method": method}).status_code == 403
                assert client.post(f"/api/orb/credits/quotes/{quote.json()['quote_id']}/verify",
                                   headers={**headers, "Origin": rejected}, json={"tx_hash": TX_HASH}).status_code == 403
        assert client.post("/api/orb/wallet/logout", headers={**headers, "Origin": X}).status_code == 403
        assert client.post("/api/orb/wallet/logout", headers=headers).status_code == 200
        assert client.get("/api/orb/credits/balance", headers=headers).status_code == 401


@pytest.mark.parametrize("origin,method", [(A, "native_eth"), (B, "native_eth"), (A, "usdg"), (B, "usdg")])
def test_both_payment_methods_keep_verification_and_idempotency(ledger, origin, method):
    service, wallet, rpc = ledger
    challenge = service.challenge(wallet.address, origin)
    session = service.sign_in(challenge["nonce"], signature(wallet, challenge), origin)
    address = service.authenticate("Bearer " + session["token"])
    quote = service.create_quote(address, 3, method)
    if method == "usdg":
        rpc.paid_usdg(quote, wallet)
        assert quote["amount_base_units"] == str(service.config.usdg_price * 3)
    else:
        rpc.paid(quote, wallet, service.config.receiver)
        assert quote["value_wei"] == str(service.config.price_wei * 3)
    assert service.verify_purchase(address, quote["quote_id"], TX_HASH)["balance"]["available"] == 3
    assert service.verify_purchase(address, quote["quote_id"], TX_HASH)["balance"]["granted"] == 3
    assert service.reserve(address, "decode", "a" * 32, "fingerprint", "job") == ("job", True)
    assert service.reserve(address, "decode", "a" * 32, "fingerprint", "job") == ("job", False)
    service.settle("job", True)
    service.settle("job", True)
    assert service.balance(address)["available"] == 2
    assert service.balance(address)["consumed"] == 1


@pytest.mark.parametrize("invalid", ["*", f"{B},", B + "/path", "http://localhost:5174", B + "?x=1"])
def test_invalid_public_origins_fail_startup_before_any_database_access(monkeypatch, tmp_path, invalid):
    configure_production(monkeypatch, tmp_path)
    monkeypatch.setenv("ORB_ADDITIONAL_PUBLIC_ORIGINS", invalid)
    def unexpected_database_access(*args, **kwargs):
        pytest.fail("Invalid origin configuration reached the database")
    monkeypatch.setattr("prometheus.api.app.CreditService", unexpected_database_access)
    with pytest.raises(RuntimeError, match="trusted HTTPS"):
        create_app(output_dir=tmp_path / "scratch")


def test_valid_public_additional_origins_need_no_new_database_configuration(monkeypatch, tmp_path):
    uploads = configure_production(monkeypatch, tmp_path)
    monkeypatch.setenv("ORB_ADDITIONAL_PUBLIC_ORIGINS", B)
    validate_public_deployment(uploads, POSTGRES_URL)


def test_malformed_primary_path_is_not_stripped_before_validation(monkeypatch, tmp_path):
    monkeypatch.setenv("ORB_PUBLIC_ORIGIN", A + "//")
    with pytest.raises(OriginError):
        create_app(provider="mock", output_dir=tmp_path / "output", upload_dir=tmp_path / "uploads")


def test_staging_cannot_add_production_origin_to_bypass_existing_isolation(ledger):
    service, _, _ = ledger
    with pytest.raises(ValueError, match="isolated staging"):
        replace(service.config, deployment_target="usdg-staging",
                additional_public_origins="https://orb-azure-ten.vercel.app")


def test_local_legacy_cors_does_not_grant_wallet_authorization(ledger, tmp_path, monkeypatch):
    service, wallet, _ = ledger
    monkeypatch.setenv("PROMETHEUS_CORS_ORIGINS", X)
    app = create_app(provider="mock", output_dir=tmp_path / "output", upload_dir=tmp_path / "uploads",
                     orb_credit_service=service)
    with TestClient(app) as client:
        assert client.get("/api/health", headers={"Origin": X}).headers["access-control-allow-origin"] == X
        assert client.post("/api/orb/wallet/challenge", headers={"Origin": X},
                           json={"address": wallet.address}).status_code == 403
