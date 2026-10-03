"""Real Postgres migration integration; opt in via the owned disposable runner.
RPC is mocked, AI is not called, and all records are synthetic.
"""
import os
from concurrent.futures import ThreadPoolExecutor
import uuid
import pytest
from psycopg import sql
from tests.postgres_rehearsal_support import (
    CORE_TABLES, EXPECTED_COUNTS, NATIVE_TX, TOKEN, WALLET, assert_core_unchanged,
    connect, database_url, migration, populate, safe_admin, save_report, snapshot,
)

pytestmark = pytest.mark.skipif(not os.environ.get('ORB_TEST_POSTGRES_URL'),
                               reason='Run scripts/run-postgres-rehearsal.py for owned real Postgres tests')

@pytest.fixture
def ledger():
    admin = safe_admin()
    name = 'orb_rehearsal_' + uuid.uuid4().hex
    with connect(admin, autocommit=True) as db:
        db.execute(sql.SQL('CREATE DATABASE {} TEMPLATE template0').format(sql.Identifier(name)))
    url = database_url(admin, name)
    try:
        populate(url)
        yield url
    finally:
        with connect(admin, autocommit=True) as db:
            db.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(name)))

def test_populated_migration_cli_and_application_startup(ledger, tmp_path, monkeypatch):
    before = snapshot(ledger)
    assert before['tls'] is True
    assert {k: v['count'] for k, v in before['tables'].items()} == EXPECTED_COUNTS
    save_report('pre_migration', before)
    check_before = migration(ledger, '--check')
    assert check_before['exit_code'] == 2, check_before
    assert snapshot(ledger) == before
    applied = migration(ledger)
    assert applied['exit_code'] == 0, applied
    after = snapshot(ledger)
    assert_core_unchanged(before, after)
    assert set(after['tables']) == set(CORE_TABLES) | {'usdg_quotes', 'usdg_schema_versions'}
    assert after['tables']['usdg_quotes']['count'] == 0
    assert after['tables']['usdg_schema_versions']['count'] == 1
    assert after['tables']['usdg_schema_versions']['rows'][0]['data'] == {'version': 1}
    assert after['tables']['usdg_quotes']['indexes']
    check_after = migration(ledger, '--check')
    retry = migration(ledger)
    final_check = migration(ledger, '--dry-run')
    assert check_after['exit_code'] == retry['exit_code'] == final_check['exit_code'] == 0
    assert 'no changes required' in retry['stdout']
    assert snapshot(ledger) == after
    save_report('post_migration', after)
    save_report('migration_commands', {'check_before': check_before, 'migration': applied,
                'check_after': check_after, 'retry': retry, 'final_check': final_check,
                'all_core_data_schema_and_tuple_identities_unchanged': True})
    verify_startup(ledger, after, tmp_path, monkeypatch)

def verify_startup(ledger, after, tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from prometheus.api.app import create_app
    from prometheus.api.orb_credits import CreditConfig, CreditService
    from tests.test_orb_usdg import UsdgRpc
    origin = 'https://orb-rehearsal.example.invalid'
    for name in list(os.environ):
        if name.startswith('PROMETHEUS_') or name == 'ORB_ENABLE_NIMIQ_PAYMENTS':
            monkeypatch.delenv(name, raising=False)
    for name, value in {
        'ORB_ENV': 'production', 'ORB_AI_PROVIDER': 'gemini', 'ORB_AI_MODEL': 'gemini-3.5-flash-lite',
        'GEMINI_API_KEY': 'synthetic-test-placeholder-not-a-credential', 'ORB_AI_LOCAL_TESTING': '0',
        'ORB_CREDITS_ENABLED': '1', 'ORB_DATABASE_URL': ledger, 'ORB_PUBLIC_ORIGIN': origin,
        'ORB_PAYMENT_METHODS': 'native_eth,usdg', 'ORB_UPLOAD_DIR': str(tmp_path / 'uploads'),
    }.items():
        monkeypatch.setenv(name, value)
    config = CreditConfig(database=tmp_path / 'unused.sqlite', database_url=ledger,
                         public_origin=origin, rpc_url='https://rpc.example.invalid',
                         receiver='0x' + '33' * 20, enabled=True,
                         payment_methods=('native_eth', 'usdg'))
    rpc = UsdgRpc()
    service = CreditService(config, rpc)
    app = create_app(orb_credit_service=service, output_dir=tmp_path / 'output', upload_dir=tmp_path / 'uploads')
    startup = snapshot(ledger)
    for table in ('schema_versions', 'challenges', 'sessions', 'quotes', 'purchases', 'results'):
        assert startup['tables'][table] == after['tables'][table], table
    assert all(startup['tables'][t]['count'] == after['tables'][t]['count'] for t in CORE_TABLES)
    statuses = {r['data']['job_id']: r['data']['status'] for r in startup['tables']['reservations']['rows']}
    assert statuses['recoverable-decode'] == 'consumed'
    assert statuses['interrupted-video'] == 'released'
    assert service.balance(WALLET)['available'] == 7
    headers = {'Origin': origin, 'Authorization': 'Bearer ' + TOKEN}
    with TestClient(app, base_url=origin) as client:
        health = client.get('/api/health')
        assert health.status_code == 200
        payment_config = client.get('/api/orb/credits/config').json()
        assert payment_config['enabled'] is True
        assert set(payment_config['payment_methods']) == {'native_eth', 'usdg'}
        balance = client.get('/api/orb/credits/balance', headers=headers)
        assert balance.status_code == 200 and balance.json()['available'] == 7
        native = client.post(f"/api/orb/credits/quotes/{1:032x}/verify", headers=headers, json={'tx_hash': NATIVE_TX})
        assert native.status_code == 200, native.text
        assert native.json()['balance']['granted'] == 10
        assert snapshot(ledger) == startup  # native replay cannot grant again
        quote = client.post('/api/orb/credits/quotes', headers=headers, json={'credits': 3, 'payment_method': 'usdg'})
        assert quote.status_code == 200, quote.text
        assert quote.json()['amount_base_units'] == '9000'
        assert quote.json()['value_wei'] == '0'
        recovered = client.get('/api/jobs/recoverable-decode/result', headers=headers)
        assert recovered.status_code == 200, recovered.text
        assert recovered.json()['prompt'] == 'Synthetic durable prompt for migration testing only.'
    before_restart = snapshot(ledger)
    create_app(orb_credit_service=service, output_dir=tmp_path / 'output', upload_dir=tmp_path / 'uploads')
    assert snapshot(ledger) == before_restart
    save_report('application_startup', {'config': payment_config, 'balance': balance.json(),
                'quote': quote.json(), 'before_startup': after, 'after_reconciliation': startup,
                'second_startup_unchanged': True, 'rpc_mocked': True, 'ai_called': False})

@pytest.mark.parametrize('fault', ['partial_usdg', 'incompatible_core', 'wrong_column_type', 'missing_core_table', 'unsupported_usdg_version'])
def test_migration_refuses_unexpected_schema_without_changes(ledger, fault):
    from prometheus.api.orb_database import OrbDatabase
    with connect(ledger) as db:
        if fault == 'partial_usdg':
            db.execute('CREATE TABLE orb.usdg_quotes (quote_id TEXT PRIMARY KEY)')
        elif fault == 'incompatible_core':
            db.execute('ALTER TABLE orb.quotes ADD COLUMN unexpected TEXT')
        elif fault == 'wrong_column_type':
            db.execute('ALTER TABLE orb.sessions ALTER COLUMN expires TYPE TEXT USING expires::text')
        elif fault == 'missing_core_table':
            db.execute('DROP TABLE orb.results')
        else:
            OrbDatabase._create_usdg(db, True)
            db.execute('ALTER TABLE orb.usdg_schema_versions DROP CONSTRAINT usdg_schema_versions_version_check')
            db.execute('UPDATE orb.usdg_schema_versions SET version=2')
    before = snapshot(ledger)
    check = migration(ledger, '--check')
    applied = migration(ledger)
    assert check['exit_code'] == applied['exit_code'] == 1
    assert snapshot(ledger) == before
    save_report('failure_' + fault, {'check': check, 'migration': applied, 'unchanged': True, 'before': before, 'after': snapshot(ledger)})

def test_atomic_ddl_rollback_after_first_usdg_table(ledger):
    with connect(ledger) as db:
        db.execute("""CREATE FUNCTION public.refuse_marker() RETURNS event_trigger LANGUAGE plpgsql AS $$
            BEGIN IF position('usdg_schema_versions' in current_query()) > 0 THEN
            RAISE EXCEPTION 'Synthetic marker creation failure'; END IF; END $$""")
        db.execute("""CREATE EVENT TRIGGER refuse_marker ON ddl_command_start
                   WHEN TAG IN ('CREATE TABLE') EXECUTE FUNCTION public.refuse_marker()""")
    before = snapshot(ledger)
    result = migration(ledger)
    assert result['exit_code'] == 1
    assert snapshot(ledger) == before
    assert 'usdg_quotes' not in snapshot(ledger)['tables']
    save_report('atomic_rollback', {'migration': result, 'no_partial_commit': True, 'before': before, 'after': snapshot(ledger)})

def test_concurrent_migration_retries(ledger):
    before = snapshot(ledger)
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: migration(ledger), range(2)))
    assert all(r['exit_code'] == 0 for r in results), results
    after = snapshot(ledger)
    assert_core_unchanged(before, after)
    assert after['tables']['usdg_schema_versions']['count'] == 1
    assert migration(ledger, '--check')['exit_code'] == 0
    save_report('concurrent_migrations', {'commands': results, 'unchanged_core': True, 'one_marker': True})
