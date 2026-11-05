import os
from pathlib import Path
import tempfile
import unittest
from dafeiyu.coding import container_test


@unittest.skipUnless(os.environ.get('DAFEIYU_TEST_DOCKER')=='1','需要显式启用 Docker 集成测试')
class DockerIsolation(unittest.TestCase):
    def test_real_container_boundaries(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name);os.chmod(root,0o755)
            (root/'tests').mkdir();(root/'tests/__init__.py').write_text('')
            (root/'tests/test_boundary.py').write_text('''import os,socket,unittest
class Boundaries(unittest.TestCase):
 def test_no_host_secrets_or_docker(self):
  self.assertFalse(os.path.exists('/var/run/docker.sock'))
  self.assertFalse(os.path.exists('/root/.codex/auth.json'))
 def test_project_is_readonly(self):
  with self.assertRaises(OSError):open('/work/escape','w')
 def test_rootfs_is_readonly(self):
  with self.assertRaises(OSError):open('/usr/escape','w')
 def test_network_is_blocked(self):
  with self.assertRaises(OSError):socket.create_connection(('1.1.1.1',443),timeout=2)
''')
            code,output=container_test(root.resolve(),'dafeiyu-boundary-tests')
            self.assertEqual(code,0,output)
            self.assertIn('Ran 4 tests',output)
