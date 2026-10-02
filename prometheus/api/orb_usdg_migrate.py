"""Explicit, additive USDG migration. Never imports the app or reconciles jobs.

ORB_DATABASE_URL is read only from the invoking environment; no .env is loaded.
--check uses a read-only transaction and returns 2 if the migration is needed.
Connection details and raw driver errors are never printed.
"""

from __future__ import annotations

import argparse
import os
import re
import sys

from prometheus.api.orb_database import OrbDatabase, validate_postgres_url


class MigrationError(RuntimeError):
    pass


# Exact v1 core column types/nullability; unexpected shapes require manual review.
CORE_COLUMNS = {
    "schema_versions": {"version": "integer", "applied_at": "timestamp with time zone"},
    "challenges": {"nonce": "text", "wallet": "text", "message": "text", "expires": "bigint", "used": "integer"},
    "sessions": {"token_hash": "text", "wallet": "text", "expires": "bigint"},
    "balances": {"wallet": "text", "granted": "bigint", "consumed": "bigint", "reserved": "bigint"},
    "quotes": {"id": "text", "wallet": "text", "credits": "integer", "amount_wei": "bigint", "tx_data": "text", "expires": "bigint", "tx_hash": "text"},
    "purchases": {"tx_hash": "text", "quote_id": "text", "wallet": "text", "credits": "integer", "block_number": "bigint", "granted_at": "bigint"},
    "reservations": {"job_id": "text", "wallet": "text", "operation": "text", "idem_key": "text", "fingerprint": "text", "status": "text", "created_at": "bigint", "updated_at": "bigint"},
    "results": {"job_id": "text", "payload": "jsonb", "created_at": "bigint"},
}
USDG_COLUMNS = {
    "usdg_quotes": {"quote_id": "text", "chain_id": "integer", "token_contract": "text", "token_decimals": "integer", "receiver": "text", "amount_base_units": "bigint", "created_at": "bigint", "created_block": "bigint"},
    "usdg_schema_versions": {"version": "integer"},
}
KEYS = {
    "schema_versions": ["PRIMARY KEY (version)"],
    "challenges": ["PRIMARY KEY (nonce)"], "sessions": ["PRIMARY KEY (token_hash)"],
    "balances": ["PRIMARY KEY (wallet)"],
    "quotes": ["PRIMARY KEY (id)", "UNIQUE (tx_hash)"],
    "purchases": ["PRIMARY KEY (tx_hash)", "UNIQUE (quote_id)", "FOREIGN KEY (quote_id) REFERENCES orb.quotes(id)"],
    "reservations": ["PRIMARY KEY (job_id)", "UNIQUE (wallet, idem_key)", "FOREIGN KEY (wallet) REFERENCES orb.balances(wallet)"],
    "results": ["PRIMARY KEY (job_id)", "FOREIGN KEY (job_id) REFERENCES orb.reservations(job_id)"],
    "usdg_quotes": ["PRIMARY KEY (quote_id)", "FOREIGN KEY (quote_id) REFERENCES orb.quotes(id)"],
    "usdg_schema_versions": ["PRIMARY KEY (version)"],
}
CHECKS = {
    "challenges": ["used = ANY (ARRAY[0, 1])"],
    "balances": ["granted >= 0", "consumed >= 0", "reserved >= 0", "granted >= consumed + reserved"],
    "quotes": ["credits = ANY (ARRAY[1, 3, 5])", "amount_wei > 0"],
    "purchases": ["credits = ANY (ARRAY[1, 3, 5])"],
    "reservations": ["operation = ANY (ARRAY['decode', 'compose', 'enhance'])", "status = ANY (ARRAY['reserved', 'consumed', 'released'])"],
    "results": ["jsonb_typeof(payload) = 'object'"],
    "usdg_quotes": ["chain_id = 421614", "token_decimals = 6", "amount_base_units > 0", "created_block >= 0"],
    "usdg_schema_versions": ["version = 1"],
}


def normalized(value: str) -> str:
    # pg_get_constraintdef adds expression parentheses and ::text casts.
    return re.sub(r"[\s()\"]", "", value.replace("::text", "")).lower()


def inspect_schema(connection) -> str:
    columns = connection.execute("""SELECT table_name, column_name, data_type, is_nullable
        FROM information_schema.columns WHERE table_schema='orb'""").fetchall()
    by_table = {}
    for row in columns:
        by_table.setdefault(row["table_name"], {})[row["column_name"]] = (row["data_type"], row["is_nullable"])
    if not set(CORE_COLUMNS).issubset(by_table):
        raise MigrationError("Expected Orb core schema v1 is missing; bootstrap a fresh database separately.")
    if set(by_table) - set(CORE_COLUMNS) - set(USDG_COLUMNS):
        raise MigrationError("Unexpected tables found in the Orb schema; explicit manual review is required.")
    extension = set(USDG_COLUMNS) & set(by_table)
    if extension and extension != set(USDG_COLUMNS):
        raise MigrationError("Partial USDG schema found; explicit manual review is required.")
    expected = CORE_COLUMNS | (USDG_COLUMNS if extension else {})
    for table, required in expected.items():
        shape = {name: (kind, "YES" if (table, name) == ("quotes", "tx_hash") else "NO") for name, kind in required.items()}
        if by_table[table] != shape:
            raise MigrationError("Orb table shape differs from the supported v1 schema.")
    constraints = connection.execute("""SELECT t.relname AS table_name, pg_get_constraintdef(c.oid) AS definition
        FROM pg_constraint c JOIN pg_class t ON t.oid=c.conrelid
        JOIN pg_namespace n ON n.oid=t.relnamespace WHERE n.nspname='orb'""").fetchall()
    definitions = {}
    for row in constraints:
        definitions.setdefault(row["table_name"], set()).add(normalized(row["definition"]))
    for table in expected:
        required = KEYS.get(table, []) + [f"CHECK ({expr})" for expr in CHECKS.get(table, [])]
        if not {normalized(expr) for expr in required}.issubset(definitions.get(table, set())):
            raise MigrationError("Orb schema is missing an expected integrity constraint.")
    versions = connection.execute("SELECT version FROM orb.schema_versions ORDER BY version").fetchall()
    if [row["version"] for row in versions] != [1]:
        raise MigrationError("Unsupported Orb core schema version.")
    if extension:
        versions = connection.execute("SELECT version FROM orb.usdg_schema_versions ORDER BY version").fetchall()
        if [row["version"] for row in versions] != [1]:
            raise MigrationError("Unsupported USDG extension version.")
        return "ready"
    return "migration_required"


def migrate(connection, *, check: bool = False) -> str:
    """DDL and marker are one transaction; no core rows or tables are changed."""
    try:
        if check:
            connection.execute("SET TRANSACTION READ ONLY")
        connection.execute("SET LOCAL search_path = pg_catalog")
        connection.execute("SET LOCAL lock_timeout = '10s'")
        connection.execute("SET LOCAL statement_timeout = '30s'")
        connection.execute("SELECT pg_advisory_xact_lock(749519621)")
        state = inspect_schema(connection)
        if state == "migration_required" and not check:
            # Keep parent quote schema stable while installing its foreign key.
            connection.execute("LOCK TABLE orb.quotes IN SHARE ROW EXCLUSIVE MODE")
            OrbDatabase._create_usdg(connection, True)
            if inspect_schema(connection) != "ready":
                raise MigrationError("USDG schema verification failed.")
            state = "migrated"
        if check:
            connection.rollback()
        else:
            connection.commit()
        return state
    except BaseException:
        connection.rollback()
        raise


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Explicit additive Orb USDG Postgres migration (no app startup).")
    parser.add_argument("--check", "--dry-run", dest="check", action="store_true", help="Read-only validation; exit 2 if migration is needed.")
    args = parser.parse_args(argv)
    connection = None
    try:
        url = os.environ.get("ORB_DATABASE_URL", "")
        validate_postgres_url(url)
        store = OrbDatabase.__new__(OrbDatabase)
        store.postgres_url = url
        connection = store._connect_postgres()
        state = migrate(connection, check=args.check)
        print({"ready": "Orb USDG schema is ready; no changes required.",
               "migration_required": "Orb core v1 is valid; explicit USDG migration is required (no changes made).",
               "migrated": "Orb USDG extension v1 added and verified. Existing core records preserved."}[state])
        return 2 if state == "migration_required" else 0
    except (MigrationError, ValueError) as exc:
        print(f"Migration refused: {exc}", file=sys.stderr)
        return 1
    except Exception:
        print("Migration failed; transaction rolled back. Check database access/configuration privately.", file=sys.stderr)
        return 1
    finally:
        if connection is not None:
            connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
