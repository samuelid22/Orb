"""Orb ledger connections and versioned SQL schema for SQLite or Postgres."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import parse_qs, urlparse


SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS challenges (
    nonce TEXT PRIMARY KEY, wallet TEXT NOT NULL, message TEXT NOT NULL,
    expires INTEGER NOT NULL, used INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY, wallet TEXT NOT NULL, expires INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS balances (
    wallet TEXT PRIMARY KEY, granted INTEGER NOT NULL DEFAULT 0 CHECK(granted >= 0),
    consumed INTEGER NOT NULL DEFAULT 0 CHECK(consumed >= 0),
    reserved INTEGER NOT NULL DEFAULT 0 CHECK(reserved >= 0),
    CHECK(granted >= consumed + reserved)
);
CREATE TABLE IF NOT EXISTS quotes (
    id TEXT PRIMARY KEY, wallet TEXT NOT NULL, credits INTEGER NOT NULL,
    amount_wei INTEGER NOT NULL, tx_data TEXT NOT NULL,
    expires INTEGER NOT NULL, tx_hash TEXT UNIQUE
);
CREATE TABLE IF NOT EXISTS purchases (
    tx_hash TEXT PRIMARY KEY, quote_id TEXT NOT NULL UNIQUE,
    wallet TEXT NOT NULL, credits INTEGER NOT NULL, block_number INTEGER NOT NULL,
    granted_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS reservations (
    job_id TEXT PRIMARY KEY, wallet TEXT NOT NULL, operation TEXT NOT NULL,
    idem_key TEXT NOT NULL, fingerprint TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('reserved','consumed','released')),
    created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL,
    UNIQUE(wallet, idem_key)
);
CREATE INDEX IF NOT EXISTS reservations_wallet ON reservations(wallet, status);
"""


POSTGRES_SCHEMA_V1 = (
    """CREATE TABLE orb.challenges (
        nonce TEXT PRIMARY KEY, wallet TEXT NOT NULL, message TEXT NOT NULL,
        expires BIGINT NOT NULL, used INTEGER NOT NULL DEFAULT 0 CHECK (used IN (0, 1))
    )""",
    """CREATE TABLE orb.sessions (
        token_hash TEXT PRIMARY KEY, wallet TEXT NOT NULL, expires BIGINT NOT NULL
    )""",
    "CREATE INDEX sessions_wallet ON orb.sessions(wallet)",
    """CREATE TABLE orb.balances (
        wallet TEXT PRIMARY KEY,
        granted BIGINT NOT NULL DEFAULT 0 CHECK (granted >= 0),
        consumed BIGINT NOT NULL DEFAULT 0 CHECK (consumed >= 0),
        reserved BIGINT NOT NULL DEFAULT 0 CHECK (reserved >= 0),
        CHECK (granted >= consumed + reserved)
    )""",
    """CREATE TABLE orb.quotes (
        id TEXT PRIMARY KEY, wallet TEXT NOT NULL, credits INTEGER NOT NULL CHECK (credits IN (1, 3, 5)),
        amount_wei BIGINT NOT NULL CHECK (amount_wei > 0), tx_data TEXT NOT NULL,
        expires BIGINT NOT NULL, tx_hash TEXT UNIQUE
    )""",
    "CREATE INDEX quotes_wallet ON orb.quotes(wallet)",
    """CREATE TABLE orb.purchases (
        tx_hash TEXT PRIMARY KEY, quote_id TEXT NOT NULL UNIQUE REFERENCES orb.quotes(id),
        wallet TEXT NOT NULL, credits INTEGER NOT NULL CHECK (credits IN (1, 3, 5)),
        block_number BIGINT NOT NULL, granted_at BIGINT NOT NULL
    )""",
    "CREATE INDEX purchases_wallet ON orb.purchases(wallet)",
    """CREATE TABLE orb.reservations (
        job_id TEXT PRIMARY KEY, wallet TEXT NOT NULL REFERENCES orb.balances(wallet),
        operation TEXT NOT NULL CHECK (operation IN ('decode', 'compose', 'enhance')),
        idem_key TEXT NOT NULL, fingerprint TEXT NOT NULL,
        status TEXT NOT NULL CHECK (status IN ('reserved', 'consumed', 'released')),
        created_at BIGINT NOT NULL, updated_at BIGINT NOT NULL,
        UNIQUE (wallet, idem_key)
    )""",
    "CREATE INDEX reservations_wallet ON orb.reservations(wallet, status)",
    """CREATE TABLE orb.results (
        job_id TEXT PRIMARY KEY REFERENCES orb.reservations(job_id),
        payload JSONB NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
        created_at BIGINT NOT NULL
    )""",
)


def validate_postgres_url(value: str) -> None:
    """Validate shape without ever putting credentials into an error."""
    parsed = urlparse(value)
    if (parsed.scheme not in {"postgres", "postgresql"} or not parsed.hostname
            or not parsed.path or parsed.path == "/" or parsed.fragment):
        raise ValueError("ORB_DATABASE_URL must be a Postgres connection URL.")
    try:
        parsed.port
    except ValueError as exc:
        raise ValueError("ORB_DATABASE_URL must include a valid Postgres port.") from exc
    sslmode = parse_qs(parsed.query).get("sslmode", [])
    if sslmode and sslmode[-1] not in {"require", "verify-ca", "verify-full"}:
        raise ValueError("ORB_DATABASE_URL must use TLS for Postgres.")


class DatabaseSession:
    def __init__(self, connection: Any, postgres: bool):
        self.connection = connection
        self.postgres = postgres

    def execute(self, statement: str, parameters: tuple = ()) -> Any:
        if self.postgres:
            statement = statement.replace("?", "%s")
        return self.connection.execute(statement, parameters)

    def begin_write(self) -> None:
        if not self.postgres:
            self.connection.execute("BEGIN IMMEDIATE")

    def commit(self) -> None:
        self.connection.commit()

    def rollback(self) -> None:
        self.connection.rollback()

    def close(self) -> None:
        self.connection.close()


class OrbDatabase:
    def __init__(self, sqlite_path: Path, postgres_url: str = "", *, usdg_staging: bool = False):
        self.sqlite_path = sqlite_path
        self.postgres_url = postgres_url
        self.postgres = bool(postgres_url)
        self.usdg_staging = usdg_staging
        if self.postgres:
            validate_postgres_url(postgres_url)
            self._initialize_postgres()
        else:
            sqlite_path.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(sqlite_path, timeout=15) as setup:
                setup.execute("PRAGMA journal_mode=WAL")
                setup.executescript(SQLITE_SCHEMA)
                if usdg_staging:
                    setup.execute("BEGIN IMMEDIATE")
                    self._initialize_usdg(setup, False)

    @staticmethod
    def _initialize_usdg(connection, postgres: bool) -> None:
        """Additive staging extension v1; never adopt an existing live ledger."""
        prefix = "orb." if postgres else ""
        if postgres:
            present = connection.execute("SELECT to_regclass('orb.usdg_schema_versions') AS ledger").fetchone()["ledger"]
        else:
            present = connection.execute("SELECT name FROM sqlite_master WHERE name='usdg_schema_versions'").fetchone()
        if present:
            versions = connection.execute(f"SELECT version FROM {prefix}usdg_schema_versions").fetchall()
            values = [row["version"] if postgres else row[0] for row in versions]
            if values != [1]:
                raise RuntimeError("Unsupported USDG staging ledger version.")
            return
        for table in ("balances", "sessions", "challenges", "quotes", "purchases", "reservations"):
            if connection.execute(f"SELECT 1 FROM {prefix}{table} LIMIT 1").fetchone():
                raise RuntimeError("USDG requires an isolated fresh staging database, not an existing Orb ledger.")
        # Core schema version stays at 1. Old native-ETH code ignores these
        # extra tables; no existing table is altered or existing row updated.
        integer = "BIGINT" if postgres else "INTEGER"
        connection.execute(f"""CREATE TABLE {prefix}usdg_quotes (
            quote_id TEXT PRIMARY KEY REFERENCES {prefix}quotes(id),
            chain_id INTEGER NOT NULL CHECK(chain_id = 421614),
            token_contract TEXT NOT NULL, token_decimals INTEGER NOT NULL CHECK(token_decimals = 6),
            receiver TEXT NOT NULL, amount_base_units {integer} NOT NULL CHECK(amount_base_units > 0),
            created_at {integer} NOT NULL, created_block {integer} NOT NULL CHECK(created_block >= 0)
        )""")
        connection.execute(f"CREATE TABLE {prefix}usdg_schema_versions (version INTEGER PRIMARY KEY CHECK(version = 1))")
        connection.execute(f"INSERT INTO {prefix}usdg_schema_versions VALUES (1)")

    def _connect_postgres(self):
        try:
            import psycopg
            from psycopg.rows import dict_row

            kwargs = {"connect_timeout": 10, "row_factory": dict_row}
            if "sslmode" not in parse_qs(urlparse(self.postgres_url).query):
                kwargs["sslmode"] = "require"
            return psycopg.connect(self.postgres_url, **kwargs)
        except Exception:
            raise RuntimeError("Orb could not connect to its production Postgres database.") from None

    def _initialize_postgres(self) -> None:
        connection = self._connect_postgres()
        try:
            # Serializes schema initialization across simultaneous cold starts.
            connection.execute("SELECT pg_advisory_xact_lock(749519621)")
            connection.execute("CREATE SCHEMA IF NOT EXISTS orb")
            connection.execute("""CREATE TABLE IF NOT EXISTS orb.schema_versions (
                version INTEGER PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )""")
            versions = connection.execute("SELECT version FROM orb.schema_versions ORDER BY version").fetchall()
            if not versions:
                existing = connection.execute("SELECT to_regclass('orb.balances') AS ledger").fetchone()
                if existing["ledger"] is not None:
                    raise RuntimeError("Orb found an unversioned Postgres ledger; migrate it explicitly.")
                for statement in POSTGRES_SCHEMA_V1:
                    connection.execute(statement)
                connection.execute("INSERT INTO orb.schema_versions(version) VALUES (1)")
            elif [row["version"] for row in versions] != [1]:
                raise RuntimeError("Orb Postgres schema version is unsupported; migrate it explicitly.")
            if getattr(self, "usdg_staging", False):
                self._initialize_usdg(connection, True)
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    @contextmanager
    def session(self) -> Iterator[DatabaseSession]:
        if self.postgres:
            connection = self._connect_postgres()
            try:
                connection.execute("SET search_path TO orb, public")
            except BaseException:
                connection.close()
                raise
        else:
            connection = sqlite3.connect(self.sqlite_path, timeout=15, isolation_level=None)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA busy_timeout=15000")
            connection.execute("PRAGMA foreign_keys=ON")
        session = DatabaseSession(connection, self.postgres)
        try:
            yield session
            session.commit()
        except BaseException:
            session.rollback()
            raise
        finally:
            session.close()
