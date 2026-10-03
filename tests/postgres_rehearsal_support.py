"""Synthetic populated production-v1 fixtures and real Postgres snapshots.
Only the marked loopback cluster created by run-postgres-rehearsal is accepted.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.parse import urlparse, urlunparse

import psycopg
from psycopg.rows import dict_row
from psycopg import sql
from prometheus.api.orb_database import POSTGRES_SCHEMA_V1

ROOT = Path(__file__).resolve().parents[1]
WALLET = '0x' + '11' * 20
OTHER = '0x' + '22' * 20
TOKEN = 'synthetic-orb-rehearsal-session-' + 'x' * 32
NATIVE_TX = '0x' + 'aa' * 32
CORE_TABLES = ('schema_versions', 'challenges', 'sessions', 'balances', 'quotes', 'purchases', 'reservations', 'results')
EXPECTED_COUNTS = dict(zip(CORE_TABLES, (1, 2, 2, 2, 4, 3, 6, 4)))

def connect(url, **kwargs):
    return psycopg.connect(url, row_factory=dict_row, **kwargs)

def safe_admin():
    url = os.environ['ORB_TEST_POSTGRES_URL']
    parsed = urlparse(url)
    if (parsed.scheme != 'postgresql' or parsed.hostname != '127.0.0.1'
            or not parsed.port or parsed.port < 49152 or parsed.path != '/orb_rehearsal_admin'
            or parsed.username != 'orb_rehearsal' or parsed.password
            or parsed.query != 'sslmode=require' or not os.environ.get('ORB_TEST_POSTGRES_RUN_ID')):
        raise RuntimeError('Only the owned local disposable rehearsal cluster is allowed.')
    with connect(url) as db:
        marker = db.execute('SELECT run_id FROM public.orb_rehearsal_cluster').fetchall()
    if marker != [{'run_id': os.environ['ORB_TEST_POSTGRES_RUN_ID']}]:
        raise RuntimeError('Disposable cluster ownership marker mismatch.')
    return url

def database_url(admin, name):
    return urlunparse(urlparse(admin)._replace(path='/' + name))

def populate(url):
    now = int(time.time())
    with connect(url) as db:
        db.execute('CREATE SCHEMA orb')
        db.execute('CREATE TABLE orb.schema_versions (version INTEGER PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())')
        for statement in POSTGRES_SCHEMA_V1:
            db.execute(statement)
        db.execute('INSERT INTO orb.schema_versions(version) VALUES (1)')
        for index, wallet in enumerate((WALLET, OTHER)):
            db.execute('INSERT INTO orb.challenges VALUES (%s,%s,%s,%s,1)',
                       (f'synthetic-nonce-{index}', wallet, 'Synthetic signed challenge fixture', now + 86400))
            token = TOKEN if index == 0 else TOKEN + '-other'
            db.execute('INSERT INTO orb.sessions VALUES (%s,%s,%s)',
                       (hashlib.sha256(token.encode()).hexdigest(), wallet, now + 86400))
        db.execute('INSERT INTO orb.balances VALUES (%s,10,2,2),(%s,3,1,0)', (WALLET, OTHER))
        for index, (wallet, credits, tx_hash) in enumerate([
                (WALLET, 5, NATIVE_TX), (WALLET, 5, '0x' + 'bb' * 32),
                (OTHER, 3, '0x' + 'cc' * 32), (WALLET, 1, None)], start=1):
            quote_id = f'{index:032x}'
            db.execute('INSERT INTO orb.quotes VALUES (%s,%s,%s,%s,%s,%s,%s)',
                       (quote_id, wallet, credits, credits * 10**12, '0x4f524231' + quote_id, now + 900, tx_hash))
            if tx_hash:
                db.execute('INSERT INTO orb.purchases VALUES (%s,%s,%s,%s,%s,%s)',
                           (tx_hash, quote_id, wallet, credits, 123456 + index, now - 3600))
        for job, wallet, operation, status, result in [
                ('completed-decode', WALLET, 'decode', 'consumed', True),
                ('completed-enhance', WALLET, 'enhance', 'consumed', True),
                ('failed-compose', WALLET, 'compose', 'released', False),
                ('recoverable-decode', WALLET, 'decode', 'reserved', True),
                ('interrupted-video', WALLET, 'decode', 'reserved', False),
                ('other-complete', OTHER, 'compose', 'consumed', True)]:
            db.execute('INSERT INTO orb.reservations VALUES (%s,%s,%s,%s,%s,%s,%s,%s)',
                       (job, wallet, operation, 'idem-' + job, 'fingerprint-' + job, status, now - 600, now - 600))
            if result:
                payload = {'job_id': job, 'operation': operation,
                           'prompt': 'Synthetic durable prompt for migration testing only.'}
                db.execute('INSERT INTO orb.results VALUES (%s,%s::jsonb,%s)', (job, json.dumps(payload), now - 500))

def snapshot(url):
    with connect(url) as db:
        result = {'server_version': db.execute('SHOW server_version').fetchone()['server_version'],
                  'tls': db.execute('SELECT ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid()').fetchone()['ssl'], 'tables': {}}
        tables = db.execute("SELECT tablename FROM pg_tables WHERE schemaname='orb' ORDER BY tablename").fetchall()
        for item in tables:
            table = item['tablename']
            rows = db.execute(sql.SQL('SELECT row_to_json(t) AS data, ctid::text AS ctid, xmin::text AS xmin FROM orb.{} t ORDER BY row_to_json(t)::text').format(sql.Identifier(table))).fetchall()
            relation = db.execute("SELECT c.oid, pg_relation_filenode(c.oid) AS filenode FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='orb' AND c.relname=%s", (table,)).fetchone()
            columns = db.execute("SELECT column_name,data_type,is_nullable,column_default FROM information_schema.columns WHERE table_schema='orb' AND table_name=%s ORDER BY ordinal_position", (table,)).fetchall()
            constraints = db.execute("SELECT conname,pg_get_constraintdef(oid) AS definition FROM pg_constraint WHERE conrelid=%s ORDER BY conname", (relation['oid'],)).fetchall()
            indexes = db.execute("SELECT indexname,indexdef FROM pg_indexes WHERE schemaname='orb' AND tablename=%s ORDER BY indexname", (table,)).fetchall()
            result['tables'][table] = {'count': len(rows), 'rows': rows, 'relation': relation,
                                      'columns': columns, 'constraints': constraints, 'indexes': indexes}
        return result

def save_report(name, payload):
    directory = Path(os.environ['ORB_TEST_POSTGRES_REPORT_DIR'])
    directory.mkdir(parents=True, exist_ok=True)
    (directory / (name + '.json')).write_text(json.dumps(payload, indent=2, sort_keys=True), encoding='utf-8')

def migration(url, *arguments):
    env = {k: v for k, v in os.environ.items()
           if not k.upper().startswith(('ORB_', 'PROMETHEUS_', 'PG'))
           and k.upper() not in {'GEMINI_API_KEY', 'GOOGLE_API_KEY', 'OPENAI_API_KEY'} }
    env['ORB_DATABASE_URL'] = url
    result = subprocess.run([sys.executable, '-m', 'prometheus.api.orb_usdg_migrate', *arguments],
                            cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)
    return {'exit_code': result.returncode, 'stdout': result.stdout.strip(), 'stderr': result.stderr.strip()}

def assert_core_unchanged(before, after):
    for table in CORE_TABLES:
        assert after['tables'][table] == before['tables'][table], table
