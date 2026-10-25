"""Operations regression tests; equivalent isolation via TemporaryDirectory.

No app import, business database access, Docker daemon or production directory.
"""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import sqlite3
import tarfile
import tempfile
import types
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('ubuntu_manage', Path(__file__).with_name('manage.py'))
ops = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ops)


class OperationsTests(unittest.TestCase):
    @contextlib.contextmanager
    def connect(self):
        with contextlib.closing(sqlite3.connect(self.db)) as db:
            with db:
                yield db

    def setUp(self):
        isolated = Path(__file__).resolve().parents[2] / 'tmp'
        isolated.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix='deploy-test-', dir=isolated)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name in ('shared/data', 'shared/uploads', 'shared/config', 'shared/control', 'backups', 'releases/v1'):
            (self.root / name).mkdir(parents=True)
        self.key = self.root / 'external.key'
        self.key.write_text('test-only-key-not-for-production\n')
        self.patch_root = patch.object(ops, 'ROOT', self.root)
        self.patch_key = patch.object(ops, 'KEY', self.key)
        self.patch_root.start()
        self.patch_key.start()
        self.addCleanup(self.patch_root.stop)
        self.addCleanup(self.patch_key.stop)
        self.db = self.root / 'shared/data/eval_platform.db'
        with self.connect() as db:
            for name in ('eval_tasks', 'agent_runs', 'batch_jobs'):
                db.execute(f'CREATE TABLE {name}(status TEXT)')
        (self.root / 'releases/v1/manifest.json').write_text('{"version":"v1"}')

    def test_version_rejects_traversal_shell_and_uppercase(self):
        for value in ('../x', '/tmp/x', 'x\ny', 'x;id', 'Version', 'a' * 65, ''):
            with self.subTest(value=value), self.assertRaises(ValueError):
                ops.valid_version(value)
        self.assertEqual(ops.valid_version('2026.10.25-1'), '2026.10.25-1')

    def test_active_work_blocks_without_business_writes(self):
        for table, status in (('eval_tasks', 'running'), ('eval_tasks', 'queued'),
                              ('agent_runs', 'waiting'), ('batch_jobs', 'pending')):
            with self.connect() as db:
                db.execute(f'INSERT INTO {table} VALUES (?)', (status,))
            before = self.db.read_bytes()
            with self.assertRaisesRegex(RuntimeError, 'Active work'):
                ops.idle()
            self.assertEqual(self.db.read_bytes(), before)
            with self.connect() as db:
                db.execute(f'DELETE FROM {table}')

    def test_completed_work_does_not_block(self):
        with self.connect() as db:
            db.execute("INSERT INTO eval_tasks VALUES ('success')")
            db.execute("INSERT INTO agent_runs VALUES ('failed')")
        ops.idle()

    def test_corrupt_database_fails_integrity_check(self):
        self.db.write_bytes(b'not a database')
        with self.assertRaises(sqlite3.DatabaseError):
            ops.check_db(self.db)

    def test_hmac_changes_if_archive_modified(self):
        archive = self.root / 'sample.enc'
        archive.write_bytes(b'original')
        before = ops.signature(archive)
        archive.write_bytes(b'changed')
        self.assertNotEqual(ops.signature(archive), before)

    def test_tampered_backup_rejected_before_decryption(self):
        backup = self.root / 'backups/bad'
        backup.mkdir()
        (backup / 'snapshot.enc').write_bytes(b'corrupted')
        (backup / 'manifest.json').write_text(json.dumps({'hmac_sha256': '0' * 64}))
        with patch.object(ops, 'run') as command:
            with self.assertRaisesRegex(RuntimeError, 'HMAC'):
                ops.unpack_snapshot(backup, self.root)
            command.assert_not_called()

    def test_active_work_keeps_backend_running_and_restores_access(self):
        with self.connect() as db:
            db.execute("INSERT INTO agent_runs VALUES ('running')")
        with patch.object(ops.time, 'sleep'), patch.object(ops, 'compose') as compose:
            with self.assertRaises(RuntimeError):
                ops.stop_idle(self.root / 'releases/v1')
            compose.assert_not_called()
        self.assertFalse((self.root / 'shared/control/maintenance').exists())

    def test_preexisting_maintenance_preserved_if_active_work_blocks(self):
        ops.maintenance(True)
        with self.connect() as db:
            db.execute("INSERT INTO agent_runs VALUES ('running')")
        with patch.object(ops.time, 'sleep'), self.assertRaises(RuntimeError):
            ops.stop_idle(self.root / 'releases/v1')
        self.assertTrue((self.root / 'shared/control/maintenance').exists())

    def test_readiness_failure_is_not_success(self):
        with patch.object(ops, 'container', return_value='test'), patch.object(
            ops, 'output', return_value='[{"State":{"Status":"exited"}}]'
        ):
            with self.assertRaisesRegex(RuntimeError, 'Readiness failed'):
                ops.wait_ready(self.root)

    def test_post_shutdown_race_leaves_maintenance_enabled(self):
        with patch.object(ops.time, 'sleep'), patch.object(ops, 'compose') as compose, patch.object(
            ops, 'idle', side_effect=[None, RuntimeError('new queued task')]
        ):
            with self.assertRaisesRegex(RuntimeError, 'new queued task'):
                ops.stop_idle(self.root / 'releases/v1')
            compose.assert_called_once_with(self.root / 'releases/v1', 'stop', 'backend')
        self.assertTrue((self.root / 'shared/control/maintenance').exists())

    def test_restore_preview_does_not_stop_or_replace_state(self):
        def unpack(backup, target):
            return 'v1'
        # Windows sandbox denies strict directory realpath handles; path
        # resolution is unrelated to this preview/control-flow regression.
        path_arg = types.SimpleNamespace(resolve=lambda **kwargs: self.root / 'backups')
        args = types.SimpleNamespace(backup=path_arg, confirm=None)
        with patch.object(ops, 'unpack_snapshot', side_effect=unpack), patch.object(ops, 'stop_idle') as stop:
            with self.assertRaisesRegex(RuntimeError, 'Preview only'):
                ops.restore(args)
            stop.assert_not_called()
        self.assertTrue(self.db.exists())

    def test_archive_traversal_rejected_after_authenticated_input(self):
        backup = self.root / 'backups/unsafe'
        backup.mkdir()
        archive = backup / 'snapshot.enc'
        with tarfile.open(archive, 'w:gz') as tar:
            member = tarfile.TarInfo('../escape')
            member.size = 1
            tar.addfile(member, io.BytesIO(b'x'))
        (backup / 'manifest.json').write_text(json.dumps({'hmac_sha256': ops.signature(archive)}))
        target = self.root / 'extract'
        target.mkdir()
        # Only decryption is replaced: this case tests archive member validation.
        def decrypt(args):
            shutil.copy2(archive, args[args.index('-out') + 1])
        with patch.object(ops, 'run', side_effect=decrypt):
            with self.assertRaisesRegex(RuntimeError, 'Unsafe backup member'):
                ops.unpack_snapshot(backup, target)
        self.assertFalse((self.root / 'escape').exists())

    def test_install_does_not_overwrite_existing_installation(self):
        with self.assertRaisesRegex(RuntimeError, 'Existing installation'):
            ops.install(types.SimpleNamespace())

    def test_release_integrity_rejects_edited_compose(self):
        release = self.root / 'releases/v1'
        meta = {'version': 'v1', 'backend': {'tag': 'backend:v1', 'id': 'sha256:a'},
                'web': {'tag': 'web:v1', 'id': 'sha256:a'}, 'compose_sha256': 'bad'}
        (release / 'manifest.json').write_text(json.dumps(meta))
        (release / 'images.env').write_text('BACKEND_IMAGE=backend:v1\nWEB_IMAGE=web:v1\n')
        (release / 'compose.yaml').write_text('changed')
        with patch.object(ops, 'output', return_value='sha256:a'):
            with self.assertRaisesRegex(RuntimeError, 'compose.yaml differs'):
                ops.image_check(release)

    @unittest.skipUnless(shutil.which('openssl'), 'OpenSSL not available on this test host')
    def test_real_encrypted_backup_roundtrip(self):
        (self.root / 'shared/uploads/evidence.txt').write_text('measured evidence')
        (self.root / 'shared/config/backend.env').write_text('SECRET_KEY=test-only')
        backup = ops.snapshot(self.root / 'releases/v1')
        target = self.root / 'verify'
        target.mkdir()
        self.assertEqual(ops.unpack_snapshot(backup, target), 'v1')
        self.assertEqual((target / 'uploads/evidence.txt').read_text(), 'measured evidence')
        self.assertEqual((target / 'config/backend.env').read_text(), 'SECRET_KEY=test-only')
        self.assertNotIn(b'SECRET_KEY', (backup / 'snapshot.enc').read_bytes())
        self.assertFalse(list((self.root / 'backups').glob('.snapshot-*')))


if __name__ == '__main__':
    unittest.main()
