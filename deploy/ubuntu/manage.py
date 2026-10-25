#!/usr/bin/env python3
"""Ubuntu single-host operations. Python stdlib only; never edits business rows."""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import getpass
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import time

ROOT = Path('/opt/eval-platform')
KEY = Path('/etc/eval-platform/backup.key')
HERE = Path(__file__).resolve().parent
VERSION = re.compile(r'[a-z0-9][a-z0-9_.-]{0,63}\Z')


def run(args, **kwargs):
    return subprocess.run([str(x) for x in args], check=True, **kwargs)


def output(args):
    return run(args, capture_output=True, text=True).stdout.strip()


def write_json(path, value):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    temp.replace(path)


def valid_version(value):
    if not VERSION.fullmatch(value):
        raise ValueError('Version must be 1-64 lowercase letters, digits, dots, underscores or hyphens')
    return value


def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def signature(path):
    result = hmac.new(KEY.read_bytes(), digestmod='sha256')
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def compose(release, *args, **kwargs):
    return run(['docker', 'compose', '--project-name', 'eval-platform', '--env-file',
                release / 'images.env', '-f', release / 'compose.yaml', *args], **kwargs)


def current():
    path = ROOT / 'current'
    if not path.is_symlink():
        raise RuntimeError('No current release. Run install first.')
    return path.resolve(strict=True)


def select_release(release):
    link = ROOT / 'current.next'
    link.unlink(missing_ok=True)
    link.symlink_to(release, target_is_directory=True)
    link.replace(ROOT / 'current')


def maintenance(on):
    flag = ROOT / 'shared/control/maintenance'
    if on:
        flag.touch()
    else:
        flag.unlink(missing_ok=True)


def container(release, service='backend'):
    result = compose(release, 'ps', '-q', service, capture_output=True, text=True)
    cid = result.stdout.strip()
    if not cid:
        raise RuntimeError(f'{service} is not running')
    return cid


def wait_ready(release):
    cid = container(release)
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        state = json.loads(output(['docker', 'inspect', cid]))[0]['State']
        if state.get('Health', {}).get('Status') == 'healthy':
            return
        if state['Status'] in ('exited', 'dead'):
            break
        time.sleep(3)
    raise RuntimeError('Readiness failed; inspect logs. Maintenance remains enabled.')


def idle():
    """Read-only global gate: includes queued work and unattended monitors."""
    path = ROOT / 'shared/data/eval_platform.db'
    if not path.exists():
        return
    with contextlib.closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as db:
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        checks = {
            'eval_tasks': "status IN ('queued','running','pending')",
            'agent_runs': "status IN ('queued','running','waiting')",
            'batch_jobs': "status IN ('queued','running','pending')",
        }
        active = {}
        for table, condition in checks.items():
            if table in tables:
                count = db.execute(f'SELECT count(*) FROM {table} WHERE {condition}').fetchone()[0]
                if count:
                    active[table] = count
        if active:
            raise RuntimeError(f'Active work blocks operation: {active}. Resolve through business APIs/UI, then retry.')


def stop_idle(release):
    was_maintenance = (ROOT / 'shared/control/maintenance').exists()
    maintenance(True)
    # Allow ordinary incoming requests to finish. Long tasks are detected below.
    time.sleep(5)
    try:
        idle()
    except Exception:
        # Nothing has been stopped or changed yet. A busy nightly backup must
        # not lock users out of a healthy running release.
        if not was_maintenance:
            maintenance(False)
        raise
    compose(release, 'stop', 'backend')
    # Recheck after shutdown; never copy an active SQLite file or change task state.
    idle()


def check_db(path):
    with contextlib.closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as db:
        if db.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
            raise RuntimeError('SQLite integrity check failed')


def snapshot(release):
    """Caller must hold operation lock and have stopped backend."""
    check_db(ROOT / 'shared/data/eval_platform.db')
    if not KEY.exists():
        raise RuntimeError('Missing encryption key; do not generate a replacement for existing backups')
    for part in ('data', 'uploads', 'config'):
        if any(entry.is_symlink() for entry in (ROOT / 'shared' / part).rglob('*')):
            raise RuntimeError('Snapshot source must not contain symlinks; install real certificate/data files')
    name = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    dest = ROOT / 'backups' / name
    dest.mkdir(mode=0o700)
    # Unencrypted staging is root-only and removed even on encryption failure.
    with tempfile.TemporaryDirectory(prefix='.snapshot-', dir=ROOT / 'backups') as tmp:
        archive = Path(tmp) / 'snapshot.tar.gz'
        with tarfile.open(archive, 'w:gz', dereference=True) as tar:
            for part in ('data', 'uploads', 'config'):
                tar.add(ROOT / 'shared' / part, arcname=part)
            tar.add(release, arcname='release')
        encrypted = dest / 'snapshot.enc'
        run(['openssl', 'enc', '-aes-256-cbc', '-pbkdf2', '-iter', '200000', '-salt',
             '-in', archive, '-out', encrypted, '-pass', f'file:{KEY}'])
    write_json(dest / 'manifest.json', {
        'created_utc': name, 'version': release.name,
        'sha256': digest(encrypted), 'hmac_sha256': signature(encrypted),
        'format': 1,
    })
    print(f'Encrypted backup: {dest}')
    return dest


def unpack_snapshot(backup, target):
    meta = json.loads((backup / 'manifest.json').read_text())
    encrypted = backup / 'snapshot.enc'
    if not hmac.compare_digest(meta['hmac_sha256'], signature(encrypted)):
        raise RuntimeError('Backup HMAC verification failed')
    archive = target / 'snapshot.tar.gz'
    run(['openssl', 'enc', '-d', '-aes-256-cbc', '-pbkdf2', '-iter', '200000',
         '-in', encrypted, '-out', archive, '-pass', f'file:{KEY}'])
    with tarfile.open(archive) as tar:
        for member in tar.getmembers():
            path = Path(member.name)
            if path.is_absolute() or '..' in path.parts or member.issym() or member.islnk() or member.isdev():
                raise RuntimeError('Unsafe backup member')
        tar.extractall(target, filter='data')
    archive.unlink()
    check_db(target / 'data/eval_platform.db')
    # Version comes from authenticated archive, not unsigned sidecar metadata.
    return json.loads((target / 'release/manifest.json').read_text())['version']


def image_check(release):
    meta = json.loads((release / 'manifest.json').read_text())
    valid_version(meta['version'])
    for service in ('backend', 'web'):
        actual = output(['docker', 'image', 'inspect', '--format', '{{.Id}}', meta[service]['tag']])
        if actual != meta[service]['id']:
            raise RuntimeError(f'{service} image differs from release manifest')
    expected = f"BACKEND_IMAGE={meta['backend']['tag']}\nWEB_IMAGE={meta['web']['tag']}\n"
    if (release / 'images.env').read_text() != expected:
        raise RuntimeError('images.env differs from manifest')
    if digest(release / 'compose.yaml') != meta['compose_sha256']:
        raise RuntimeError('compose.yaml differs from manifest')
    compose(release, 'config', '--quiet')


def stage(package):
    package = package.resolve(strict=True)
    meta = json.loads((package / 'manifest.json').read_text())
    version = valid_version(meta['version'])
    target = ROOT / 'releases' / version
    if target.exists():
        raise RuntimeError(f'Release already exists: {target}; use a new version')
    if digest(package / 'images.tar') != meta['images_sha256']:
        raise RuntimeError('Release images.tar checksum mismatch')
    run(['docker', 'load', '-i', package / 'images.tar'])
    target.mkdir(mode=0o700, parents=True)
    for name in ('manifest.json', 'images.env', 'compose.yaml'):
        shutil.copy2(package / name, target / name)
    image_check(target)
    return target


def rehearsal(release):
    """Test startup migration against a stopped, isolated copy. No worker/network."""
    with tempfile.TemporaryDirectory(prefix='.rehearsal-', dir=ROOT) as tmp:
        state = Path(tmp)
        for part in ('data', 'uploads'):
            shutil.copytree(ROOT / 'shared' / part, state / part)
        (state / 'logs').mkdir()
        chown_tree(state)
        image = json.loads((release / 'manifest.json').read_text())['backend']['tag']
        run(['docker', 'run', '--rm', '--network', 'none', '--env-file',
             ROOT / 'shared/config/backend.env', '-e', 'AGENT_WORKER_ENABLED=false',
             '-v', f'{state}:/state', image, 'python', '-c',
             'import asyncio; from app.database import init_db, seed_db; '
             'from app.services.prod_guards import assert_production_safe; '
             'assert_production_safe(); asyncio.run(init_db()); asyncio.run(seed_db())'])
        check_db(state / 'data/eval_platform.db')


def chown_tree(path):
    for entry in [path, *path.rglob('*')]:
        if not entry.is_symlink():
            os.chown(entry, 10001, 10001)


def smoke(release, username, password):
    wait_ready(release)
    compose(release, 'exec', '-T', 'web', 'nginx', '-t')
    # Avoid printing credentials or tokens; use stdin instead of argv/environment.
    program = """import json, sys, urllib.request
p = json.load(sys.stdin)
req = urllib.request.Request('http://127.0.0.1:8000/api/auth/login',
    data=json.dumps(p).encode(), headers={'Content-Type':'application/json'})
with urllib.request.urlopen(req, timeout=20) as response:
    assert json.load(response).get('access_token'), 'Missing login token'
print('Login smoke passed')
"""
    run(['docker', 'exec', '-i', container(release), 'python', '-c', program],
        input=json.dumps({'username': username, 'password': password}), text=True)
    # Verify actual frontend artifact; curl the public HTTPS endpoint after release.
    compose(release, 'exec', '-T', 'web', 'test', '-s', '/usr/share/nginx/html/index.html')


def build(args):
    valid_version(args.version)
    source = HERE.parents[1]
    target = args.output.resolve() / args.version
    target.mkdir(parents=True, exist_ok=False)
    meta = {'version': args.version, 'git_commit': output(['git', '-C', source, 'rev-parse', 'HEAD']),
            'dirty': bool(output(['git', '-C', source, 'status', '--porcelain'])),
            'platform': args.platform, 'built_utc': dt.datetime.now(dt.timezone.utc).isoformat()}
    with tempfile.TemporaryDirectory() as tmp:
        for service, folder in (('backend', 'backend'), ('web', 'frontend')):
            context = Path(tmp) / service
            context.mkdir()
            items = ('app', 'requirements.lock.txt') if service == 'backend' else (
                'src', 'public', 'scripts', 'package.json', 'package-lock.json', 'index.html', 'vite.config.js')
            for item in items:
                src = source / folder / item
                if src.is_dir():
                    shutil.copytree(src, context / item,
                                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '.env*', '*.log'))
                else:
                    shutil.copy2(src, context / item)
            shutil.copy2(HERE / '.dockerignore', context / '.dockerignore')
        # Both images must use the same collected permission catalog. Running
        # prebuild only inside the frontend image would leave backend stale.
        run(['docker', 'run', '--rm', '--platform', args.platform, '--network', 'none',
             '-v', f'{Path(tmp).resolve()}:/workspace', '-w', '/workspace/web',
             'node:22-bookworm-slim', 'node', 'scripts/collect-permissions.js'])
        for service in ('backend', 'web'):
            context = Path(tmp) / service
            tag = f'eval-platform-{service}:{args.version}'
            # Refuse reusing a local release tag.
            exists = subprocess.run(['docker', 'image', 'inspect', tag], capture_output=True).returncode == 0
            if exists:
                raise RuntimeError(f'Image tag already exists: {tag}; choose another version')
            run(['docker', 'build', '--platform', args.platform, '--pull', '-f',
                 HERE / f'{service}.Dockerfile', '-t', tag, context])
            meta[service] = {'tag': tag, 'id': output(['docker', 'image', 'inspect', '--format', '{{.Id}}', tag])}
    run(['docker', 'save', '-o', target / 'images.tar', meta['backend']['tag'], meta['web']['tag']])
    meta['images_sha256'] = digest(target / 'images.tar')
    (target / 'images.env').write_text(
        f"BACKEND_IMAGE={meta['backend']['tag']}\nWEB_IMAGE={meta['web']['tag']}\n", encoding='utf-8')
    shutil.copy2(HERE / 'compose.yaml', target / 'compose.yaml')
    meta['compose_sha256'] = digest(target / 'compose.yaml')
    write_json(target / 'manifest.json', meta)
    shutil.copy2(HERE / 'manage.py', target / 'manage.py')
    shutil.copy2(HERE / 'nginx.conf.template', target / 'nginx.conf.template')
    for name in ('bootstrap.sh', 'eval-platform-backup.service', 'eval-platform-backup.timer', 'README.md'):
        shutil.copy2(HERE / name, target / name)
    print(f'Release package: {target}; dirty source: {meta["dirty"]}')


def install(args):
    if (ROOT / 'shared').exists():
        raise RuntimeError('Existing installation detected; install never overwrites data/config')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.-]*', args.domain):
        raise ValueError('Invalid hostname')
    for cert in (args.cert, args.key):
        if not cert.is_file():
            raise ValueError(f'Missing certificate: {cert}')
    # Fail before creating an installation if the public ports are occupied.
    for port in (80, 443):
        with socket.socket() as probe:
            probe.bind(('0.0.0.0', port))
    password = getpass.getpass('New production admin password (at least 16 characters): ')
    if len(password) < 16 or password == 'admin123' or '\n' in password or '\r' in password:
        raise ValueError('Strong bootstrap password required')
    if password != getpass.getpass('Repeat admin password: '):
        raise ValueError('Passwords differ')
    for part in ('config/tls', 'config/certs', 'data', 'uploads', 'logs', 'control'):
        (ROOT / 'shared' / part).mkdir(parents=True, mode=0o700)
    (ROOT / 'backups').mkdir(mode=0o700)
    KEY.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not KEY.exists():
        KEY.write_text(secrets.token_hex(48) + '\n')
        KEY.chmod(0o600)
    env = {
        'APP_ENV': 'production', 'SECRET_KEY': secrets.token_hex(48),
        'ADMIN_BOOTSTRAP_PASSWORD': password,
        'DATABASE_URL': 'sqlite+aiosqlite:////state/data/eval_platform.db',
        'UPLOAD_DIR': '/state/uploads', 'LOG_DIR': '/state/logs',
        'BACKUP_DIR': '/state/data/api-backups', 'LOG_LEVEL': 'INFO', 'AGENT_WORKER_ENABLED': 'true',
    }
    # Compose env_file single quotes preserve dollar signs and spaces.
    (ROOT / 'shared/config/backend.env').write_text(''.join(
        f"{k}='{v.replace(chr(39), chr(92) + chr(39))}'\n" for k, v in env.items()), encoding='utf-8')
    shutil.copy2(args.cert, ROOT / 'shared/config/tls/fullchain.pem')
    shutil.copy2(args.key, ROOT / 'shared/config/tls/privkey.pem')
    template = (HERE / 'nginx.conf.template').read_text()
    (ROOT / 'shared/config/nginx.conf').write_text(template.replace('__DOMAIN__', args.domain))
    (ROOT / 'shared/control/maintenance.html').write_text(
        '<!doctype html><meta charset="utf-8"><title>维护中</title><h1>平台维护中，请稍后重试。</h1>', encoding='utf-8')
    for part in ('data', 'uploads', 'logs'):
        chown_tree(ROOT / 'shared' / part)
    os.chown(ROOT / 'shared/config/certs', 0, 10001)
    (ROOT / 'shared/config/certs').chmod(0o750)
    # Nginx workers must traverse control to serve the maintenance document.
    (ROOT / 'shared/control').chmod(0o755)
    (ROOT / 'shared/control/maintenance.html').chmod(0o644)
    (ROOT / 'shared/config/backend.env').chmod(0o600)
    maintenance(True)
    release = stage(args.package)
    select_release(release)
    compose(release, 'up', '-d')
    smoke(release, 'admin', password)
    # Bootstrap is only used for initial creation; do not retain a reusable password.
    env_path = ROOT / 'shared/config/backend.env'
    env_path.write_text(''.join(line for line in env_path.read_text().splitlines(keepends=True)
                                if not line.startswith('ADMIN_BOOTSTRAP_PASSWORD=')))
    compose(release, 'up', '-d', '--force-recreate', 'backend')
    wait_ready(release)
    maintenance(False)
    print('Installed. Verify public HTTPS, UI, permissions and SSE. Escrow backup.key separately.')


def update(args):
    previous = current()
    release = stage(args.package)
    password = getpass.getpass('Existing smoke-test user password: ')
    write_json(ROOT / 'pending.json', {'from': previous.name, 'to': release.name, 'phase': 'prepared'})
    stop_idle(previous)
    backup = snapshot(previous)
    write_json(ROOT / 'pending.json', {'from': previous.name, 'to': release.name, 'backup': str(backup), 'phase': 'backed-up'})
    rehearsal(release)
    write_json(ROOT / 'pending.json', {'from': previous.name, 'to': release.name, 'backup': str(backup)})
    select_release(release)
    compose(release, 'up', '-d')
    smoke(release, args.username, password)
    write_json(ROOT / 'last-update.json', {'from': previous.name, 'to': release.name, 'backup': str(backup)})
    (ROOT / 'pending.json').unlink()
    maintenance(False)
    print('Updated; verify public HTTPS, permissions, SSE and core UI. No production admission claimed.')


def backup_command(args):
    release = current()
    was_maintenance = (ROOT / 'shared/control/maintenance').exists()
    stop_idle(release)
    snapshot(release)
    compose(release, 'up', '-d', 'backend')
    wait_ready(release)
    if not was_maintenance:
        maintenance(False)


def restore(args):
    backup = args.backup.resolve(strict=True)
    # Verify and decrypt before stopping current service or touching live data.
    with tempfile.TemporaryDirectory(prefix='.restore-', dir=ROOT) as tmp:
        staged = Path(tmp)
        version = valid_version(unpack_snapshot(backup, staged))
        print(f'Restore version={version}, snapshot={backup.name}. All later database/file writes will be lost.')
        if args.confirm != backup.name:
            raise RuntimeError('Preview only. Repeat with --confirm SNAPSHOT_DIRECTORY_NAME to restore.')
        password = getpass.getpass('Snapshot smoke-test user password: ')
        release = ROOT / 'releases' / version
        image_check(staged / 'release')
        if release.exists() and digest(release / 'manifest.json') != digest(staged / 'release/manifest.json'):
            raise RuntimeError('Existing release manifest differs from snapshot')
        old = current()
        # Require business quiescence; no forced task cancellation.
        stop_idle(old)
        rescue = ROOT / ('rescue-' + dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
        rescue.mkdir(mode=0o700)
        # Preserve current state rather than deleting it. Rescue contains plaintext secrets.
        for part in ('data', 'uploads', 'config'):
            (ROOT / 'shared' / part).rename(rescue / part)
            shutil.move(str(staged / part), ROOT / 'shared' / part)
        for part in ('data', 'uploads'):
            chown_tree(ROOT / 'shared' / part)
        if not release.exists():
            shutil.copytree(staged / 'release', release)
        select_release(release)
        compose(release, 'up', '-d', '--force-recreate')
        smoke(release, args.username, password)
        maintenance(False)
        print(f'Restored. Preserved previous state: {rescue}; securely remove after verification.')


def rollback(args):
    release = ROOT / 'releases' / valid_version(args.version)
    image_check(release)
    if args.confirm != args.version:
        raise RuntimeError('Code-only rollback needs --confirm VERSION after confirming schema compatibility; otherwise use restore.')
    password = getpass.getpass('Existing smoke-test user password: ')
    old = current()
    stop_idle(old)
    snapshot(old)
    # Rehearsal is an operational check, not proof that downgrade semantics are safe.
    rehearsal(release)
    select_release(release)
    compose(release, 'up', '-d')
    smoke(release, args.username, password)
    maintenance(False)


def verify_backup(args):
    with tempfile.TemporaryDirectory(prefix='.verify-', dir=ROOT) as tmp:
        started = time.monotonic()
        version = unpack_snapshot(args.backup.resolve(strict=True), Path(tmp))
        print(f'Backup decrypted; SQLite integrity passed; version={version}; elapsed={time.monotonic()-started:.2f}s')
        print('This is file recovery verification, not a measured full application RTO or business acceptance.')


def resume(args):
    release = current()
    image_check(release)
    password = getpass.getpass('Current-version smoke-test user password: ')
    maintenance(True)
    compose(release, 'up', '-d')
    smoke(release, args.username, password)
    maintenance(False)
    print('Current release resumed. Pending update record, if any, is retained for investigation.')


def status(args):
    release = current()
    compose(release, 'ps')
    print(f'Current version: {release.name}; maintenance: {(ROOT / "shared/control/maintenance").exists()}')
    for name in ('pending.json', 'last-update.json'):
        if (ROOT / name).exists():
            print(f'{name}: {(ROOT / name).read_text()}')


def doctor(args):
    print(f'OS: {sys.platform}; Python: {sys.version.split()[0]}')
    print(f'Free disk: {shutil.disk_usage(ROOT if ROOT.exists() else Path("/opt")).free // 2**30} GiB')
    for command in (['docker', 'version', '--format', '{{.Server.Version}}'],
                    ['docker', 'compose', 'version'], ['openssl', 'version']):
        run(command)
    if (ROOT / 'current').exists():
        status(args)
        image_check(current())
        compose(current(), 'exec', '-T', 'web', 'nginx', '-t')
    print('No environment values, credentials, tokens or business rows are included in this diagnostic.')


def prune(args):
    """Keep seven daily snapshots and four weekly snapshots, plus update references."""
    backups = sorted((ROOT / 'backups').glob('*/manifest.json'), reverse=True)
    keep, days, weeks = set(), set(), set()
    for manifest in backups:
        stamp = dt.datetime.strptime(manifest.parent.name, '%Y%m%dT%H%M%S%fZ')
        day, week = stamp.date(), stamp.isocalendar()[:2]
        if day not in days and len(days) < 7:
            days.add(day)
            keep.add(manifest.parent)
        if week not in weeks and len(weeks) < 4:
            weeks.add(week)
            keep.add(manifest.parent)
    for name in ('pending.json', 'last-update.json'):
        if (ROOT / name).exists():
            reference = json.loads((ROOT / name).read_text()).get('backup')
            if reference:
                keep.add(Path(reference))
    for manifest in backups:
        folder = manifest.parent
        if folder not in keep:
            print(f'{"Delete" if args.confirm else "Would delete"}: {folder}')
            if args.confirm:
                if folder.is_symlink() or folder.resolve().parent != (ROOT / 'backups').resolve():
                    raise RuntimeError('Unsafe backup path')
                shutil.rmtree(folder)


@contextlib.contextmanager
def operation_lock():
    import fcntl
    ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (ROOT / '.operations.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    cmd = commands.add_parser('build', help='Build/export a versioned release; Docker required')
    cmd.add_argument('version')
    cmd.add_argument('--output', type=Path, required=True)
    cmd.add_argument('--platform', default='linux/amd64', choices=['linux/amd64', 'linux/arm64'])
    cmd = commands.add_parser('install')
    cmd.add_argument('package', type=Path)
    cmd.add_argument('--domain', required=True)
    cmd.add_argument('--cert', type=Path, required=True)
    cmd.add_argument('--key', type=Path, required=True)
    for name in ('update', 'restore', 'rollback'):
        cmd = commands.add_parser(name)
        cmd.add_argument({'update': 'package', 'restore': 'backup', 'rollback': 'version'}[name],
                         type=str if name == 'rollback' else Path)
        cmd.add_argument('--username', default='admin')
        if name != 'update':
            cmd.add_argument('--confirm')
    cmd = commands.add_parser('verify-backup')
    cmd.add_argument('backup', type=Path)
    cmd = commands.add_parser('resume', help='Explicitly restart and verify current release before reopening')
    cmd.add_argument('--username', default='admin')
    for name in ('backup', 'status', 'doctor', 'prune'):
        cmd = commands.add_parser(name)
        if name == 'prune':
            cmd.add_argument('--confirm', action='store_true')
    args = parser.parse_args()
    if args.command == 'build':
        build(args)
        return
    if sys.platform != 'linux' or os.geteuid() != 0:
        raise RuntimeError('Server operations require root on Ubuntu/Linux')
    os.umask(0o077)
    handlers = {'install': install, 'update': update, 'backup': backup_command,
                'restore': restore, 'rollback': rollback, 'verify-backup': verify_backup,
                'status': status, 'doctor': doctor, 'prune': prune, 'resume': resume}
    with operation_lock():
        handlers[args.command](args)


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, ValueError, OSError, subprocess.CalledProcessError) as exc:
        print(f'ERROR: {exc}\nIf maintenance was enabled, it remains on. Inspect status and recover explicitly.', file=sys.stderr)
        sys.exit(1)
