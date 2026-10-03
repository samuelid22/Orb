"""Migration tests use a transactional SQL/catalog double, never production."""

import copy
import pytest

from prometheus.api.orb_usdg_migrate import (
    CORE_COLUMNS, USDG_COLUMNS, KEYS, CHECKS, MigrationError, migrate, main,
)
from tests.test_orb_postgres import FakeCursor


class CatalogConnection:
    def __init__(self, extension=False):
        self.columns = copy.deepcopy(CORE_COLUMNS | (USDG_COLUMNS if extension else {}))
        self.definitions = {table: KEYS.get(table, []) + [f"CHECK (({expr}))" for expr in CHECKS.get(table, [])] for table in self.columns}
        self.versions = [1]
        self.extension_versions = [1]
        self.rows = {"balances": [{"wallet": "existing", "granted": 9, "consumed": 2, "reserved": 1}], "sessions": [{"token_hash": "existing-session"}], "quotes": [{"id": "native-quote"}], "purchases": [{"tx_hash": "native-purchase"}], "reservations": [{"job_id": "active-job"}], "results": [{"job_id": "complete-job"}]}
        self.calls = []
        self.committed = self.rolled_back = False
        self.failure = None
        self.snapshot = copy.deepcopy((self.columns, self.definitions))

    def execute(self, sql, parameters=()):
        self.calls.append(sql)
        if self.failure and self.failure in sql: raise RuntimeError("driver failure including PRIVATE_CONNECTION_VALUE")
        if "information_schema.columns" in sql:
            return FakeCursor(rows=[{"table_name": table, "column_name": column, "data_type": kind,
                "is_nullable": "YES" if (table, column) == ("quotes", "tx_hash") else "NO"}
                for table, columns in self.columns.items() for column, kind in columns.items()])
        if "pg_constraint" in sql:
            return FakeCursor(rows=[{"table_name": table, "definition": definition} for table, values in self.definitions.items() for definition in values])
        if "SELECT version FROM orb.schema_versions" in sql: return FakeCursor(rows=[{"version": value} for value in self.versions])
        if "SELECT version FROM orb.usdg_schema_versions" in sql: return FakeCursor(rows=[{"version": value} for value in self.extension_versions])
        for table in USDG_COLUMNS:
            if sql.startswith(f"CREATE TABLE orb.{table}"):
                self.columns[table] = copy.deepcopy(USDG_COLUMNS[table])
                self.definitions[table] = KEYS[table] + [f"CHECK ({expr})" for expr in CHECKS[table]]
        return FakeCursor()

    def commit(self):
        self.committed = True
        self.snapshot = copy.deepcopy((self.columns, self.definitions))

    def rollback(self):
        self.rolled_back = True
        self.columns, self.definitions = copy.deepcopy(self.snapshot)

    def close(self): pass


def test_check_is_read_only_and_identifies_populated_core_without_modifying_it():
    connection = CatalogConnection()
    rows = copy.deepcopy(connection.rows)
    assert migrate(connection, check=True) == "migration_required"
    assert connection.calls[0] == "SET TRANSACTION READ ONLY"
    assert connection.rolled_back and not connection.committed
    assert not any(sql.startswith(("CREATE", "INSERT", "UPDATE", "DELETE", "ALTER", "DROP")) for sql in connection.calls)
    assert connection.rows == rows


def test_explicit_migration_preserves_core_records_and_retries_idempotently():
    connection = CatalogConnection()
    rows = copy.deepcopy(connection.rows)
    assert migrate(connection) == "migrated"
    assert connection.committed and connection.rows == rows
    ddl = [sql for sql in connection.calls if sql.startswith("CREATE")]
    assert len(ddl) == 2 and all("orb.usdg_" in sql for sql in ddl)
    assert not any(sql.startswith(("UPDATE", "DELETE", "ALTER", "DROP")) for sql in connection.calls)
    connection.calls.clear()
    assert migrate(connection) == "ready"
    assert not any(sql.startswith(("CREATE", "INSERT")) for sql in connection.calls)
    assert migrate(connection, check=True) == "ready"


@pytest.mark.parametrize("fault", ["missing_table", "column_type", "extra_column", "extra_table", "constraint", "version", "partial", "extension_type", "extension_version"])
def test_unexpected_schema_fails_before_any_ddl(fault):
    connection = CatalogConnection(extension=fault.startswith("extension"))
    if fault == "missing_table": del connection.columns["results"]
    elif fault == "column_type": connection.columns["balances"]["granted"] = "integer"
    elif fault == "extra_column": connection.columns["quotes"]["unexpected"] = "text"
    elif fault == "extra_table": connection.columns["unexpected"] = {"id": "text"}
    elif fault == "constraint": connection.definitions["purchases"] = []
    elif fault == "version": connection.versions = [2]
    elif fault == "partial": connection.columns["usdg_quotes"] = USDG_COLUMNS["usdg_quotes"]
    elif fault == "extension_type": connection.columns["usdg_quotes"]["amount_base_units"] = "integer"
    else: connection.extension_versions = [2]
    with pytest.raises(MigrationError): migrate(connection)
    assert connection.rolled_back and not connection.committed
    assert not any(sql.startswith(("CREATE", "INSERT", "UPDATE", "DELETE", "ALTER", "DROP")) for sql in connection.calls)


def test_failed_extension_creation_rolls_back_all_schema_changes():
    connection = CatalogConnection()
    connection.failure = "CREATE TABLE orb.usdg_schema_versions"
    with pytest.raises(RuntimeError): migrate(connection)
    assert connection.rolled_back and set(connection.columns) == set(CORE_COLUMNS)


def test_cli_never_loads_env_or_prints_credentials_and_has_meaningful_exit_codes(monkeypatch, capsys):
    from prometheus.api.orb_database import OrbDatabase
    monkeypatch.delenv("ORB_DATABASE_URL", raising=False)
    assert main(["--check"]) == 1
    monkeypatch.setenv("ORB_DATABASE_URL", "postgresql://placeholder:PRIVATE_CONNECTION_VALUE@db.example.invalid/orb?sslmode=require")
    connection = CatalogConnection()
    monkeypatch.setattr(OrbDatabase, "_connect_postgres", lambda self: connection)
    assert main(["--check"]) == 2
    assert main([]) == 0
    assert main(["--dry-run"]) == 0
    connection.failure = "information_schema.columns"
    assert main([]) == 1
    output = capsys.readouterr()
    assert "PRIVATE_CONNECTION_VALUE" not in output.out + output.err
    assert "postgresql://" not in output.out + output.err
