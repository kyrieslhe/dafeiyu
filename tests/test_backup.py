import io
import os
from pathlib import Path
import stat
import tarfile
import tempfile
import unittest
from dafeiyu.backup import BackupError,safe_members,setup,snapshot,restore,maybe_backup
from dafeiyu.core import Fish


class ArchiveTests(unittest.TestCase):
    def test_reject_paths_and_links_before_extraction(self):
        for name,kind in [('../escape',tarfile.REGTYPE),('/escape',tarfile.REGTYPE),('secrets/key',tarfile.REGTYPE),('reports/link',tarfile.SYMTYPE)]:
            data=io.BytesIO()
            with tarfile.open(fileobj=data,mode='w') as archive:
                item=tarfile.TarInfo(name);item.type=kind;archive.addfile(item)
            data.seek(0)
            with tarfile.open(fileobj=data,mode='r') as archive:
                with self.assertRaises(BackupError):safe_members(archive)


@unittest.skipUnless(os.environ.get('DAFEIYU_TEST_AGE')=='1','需要显式启用 age 加密恢复集成测试')
class EncryptedRecovery(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.home=Path(self.tmp.name)/'home'
        self.fish=Fish(self.home);self.fish.remember('未来会被删除的偏好');self.fish.enqueue('reminder','喝水')
        setup(self.home)
    def tearDown(self):self.fish.close();self.tmp.cleanup()
    def test_round_trip_preserves_deletions_and_pauses_execution(self):
        encrypted=snapshot(self.home);self.fish.forget(1)
        target=Path(self.tmp.name)/'restored'
        restore(self.home,encrypted,target)
        recovered=Fish(target)
        try:
            self.assertEqual(recovered.command('/memories'),[])
            self.assertTrue(recovered.command('/status')['paused'])
            self.assertIsNone(recovered.tick())
            self.assertEqual(recovered.command('/tasks')[0]['state'],'queued')
            self.assertFalse((target/'secrets').exists())
        finally:recovered.close()
    def test_existing_target_is_never_overwritten(self):
        encrypted=snapshot(self.home)
        target=Path(self.tmp.name)/'existing';target.mkdir();(target/'keep').write_text('unchanged')
        with self.assertRaises(BackupError):restore(self.home,encrypted,target)
        self.assertEqual((target/'keep').read_text(),'unchanged')
    def test_tamper_fails_without_creating_target(self):
        encrypted=snapshot(self.home);data=bytearray(encrypted.read_bytes());data[-1]^=1;encrypted.write_bytes(data)
        target=Path(self.tmp.name)/'tampered'
        with self.assertRaises(BackupError):restore(self.home,encrypted,target)
        self.assertFalse(target.exists())
    def test_key_is_private_and_backups_are_deduplicated_per_day(self):
        key=self.home/'secrets/recovery.agekey'
        self.assertEqual(stat.S_IMODE(key.stat().st_mode),0o600)
        self.assertIsNotNone(maybe_backup(self.fish))
        self.assertIsNone(maybe_backup(self.fish))
        self.assertEqual(len(list((self.home/'backups').glob('*.age'))),1)
        self.assertEqual(stat.S_IMODE(next((self.home/'backups').glob('*.age')).stat().st_mode),0o600)


if __name__=='__main__':unittest.main()
