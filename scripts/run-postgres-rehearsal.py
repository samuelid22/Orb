"""Rehearse on an owned loopback-only disposable TLS Postgres cluster.
Never loads .env or inherits application/database/provider configuration.
"""
from __future__ import annotations
import argparse
import datetime as dt
import ipaddress
import os
from pathlib import Path
import socket
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]

def clean_environment():
    return {k: v for k, v in os.environ.items()
            if not k.upper().startswith(('ORB_', 'PROMETHEUS_', 'PG'))
            and k.upper() not in {'GEMINI_API_KEY', 'GOOGLE_API_KEY', 'OPENAI_API_KEY'}}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bin-dir', type=Path, default=ROOT / 'api_output/migration_rehearsal_runtime/pgsql/bin')
    parser.add_argument('--full-suite', action='store_true')
    args = parser.parse_args()
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
    import psycopg
    suffix = '.exe' if os.name == 'nt' else ''
    binaries = {n: args.bin_dir.resolve() / (n + suffix) for n in ('initdb', 'pg_ctl')}
    if not all(p.is_file() for p in binaries.values()):
        parser.error('Provide portable Postgres binaries; cloud databases are not supported.')
    run_id = uuid.uuid4().hex
    runtime = ROOT / 'api_output/migration_rehearsal_runtime' / run_id
    runtime.mkdir(parents=True)
    data = runtime / 'data'
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    if port < 49152:
        raise RuntimeError('Rehearsal requires a disposable high loopback port.')
    env = clean_environment()
    env.update(ORB_ENV='local', ORB_AI_PROVIDER='mock', ORB_AI_LOCAL_TESTING='0',
               ORB_CREDITS_ENABLED='0', ORB_OUTPUT_DIR=str(runtime / 'app_output'),
               ORB_UPLOAD_DIR=str(runtime / 'app_uploads'))
    def run(command):
        # Windows postgres children can inherit pipes after pg_ctl exits.
        # File handles keep subprocess completion independent of server lifetime.
        command_log = runtime / 'launcher.log'
        with command_log.open('w', encoding='utf-8') as handle:
            result = subprocess.run([str(i) for i in command], cwd=ROOT, env=env,
                                    stdout=handle, stderr=subprocess.STDOUT, timeout=120,
                                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        if result.returncode:
            raise RuntimeError('Local Postgres command failed: ' + command_log.read_text(encoding='utf-8'))
        return result
    run([binaries['initdb'], '-D', data, '-U', 'orb_rehearsal', '--auth=trust', '--locale=C', '-E', 'UTF8', '--no-sync'])
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Orb disposable rehearsal')])
    now = dt.datetime.now(dt.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - dt.timedelta(minutes=1))
            .not_valid_after(now + dt.timedelta(days=2))
            .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address('127.0.0.1'))]), critical=False)
            .sign(key, hashes.SHA256()))
    (data / 'server.key').write_bytes(key.private_bytes(serialization.Encoding.PEM,
                                  serialization.PrivateFormat.TraditionalOpenSSL, serialization.NoEncryption()))
    (data / 'server.key').chmod(0o600)
    (data / 'server.crt').write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    with (data / 'postgresql.conf').open('a', encoding='utf-8') as handle:
        handle.write(f"\nlisten_addresses = '127.0.0.1'\nport = {port}\nssl = on\n")
    started = False
    try:
        run([binaries['pg_ctl'], '-D', data, '-l', runtime / 'postgres.log', '-w', '-t', '60', 'start'])
        started = True
        base = f'postgresql://orb_rehearsal@127.0.0.1:{port}/'
        with psycopg.connect(base + 'postgres?sslmode=require', autocommit=True) as connection:
            connection.execute('CREATE DATABASE orb_rehearsal_admin')
        url = base + 'orb_rehearsal_admin?sslmode=require'
        with psycopg.connect(url) as connection:
            connection.execute('CREATE TABLE public.orb_rehearsal_cluster (run_id TEXT PRIMARY KEY)')
            connection.execute('INSERT INTO public.orb_rehearsal_cluster VALUES (%s)', (run_id,))
        env.update(ORB_TEST_POSTGRES_URL=url, ORB_TEST_POSTGRES_RUN_ID=run_id,
                   ORB_TEST_POSTGRES_REPORT_DIR=str(runtime / 'reports'))
        command = [sys.executable, '-m', 'pytest', '-q', '--tb=short']
        if not args.full_suite:
            command.append('tests/test_orb_usdg_postgres_integration.py')
        print('Disposable TLS Postgres started on loopback; no .env loaded.', flush=True)
        result = subprocess.run(command, cwd=ROOT, env=env)
        print(f"Rehearsal artifacts: {runtime / 'reports'}", flush=True)
        return result.returncode
    finally:
        if started:
            run([binaries['pg_ctl'], '-D', data, '-m', 'fast', '-w', '-t', '60', 'stop'])
            print('Owned disposable Postgres cluster stopped.', flush=True)

if __name__ == '__main__':
    raise SystemExit(main())
