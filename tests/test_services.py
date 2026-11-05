import importlib.util
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parent.parent

def load(name):
    spec=importlib.util.spec_from_file_location(name,ROOT/'scripts'/(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


class ServiceTests(unittest.TestCase):
    def test_explicit_stop_cannot_be_undone_by_internal_watchdog(self):
        module=load('services')
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            with patch.object(module,'ROOT',root),patch.object(module,'STATE',root/'var/services.json'),patch('sys.stdout',new_callable=io.StringIO),patch('subprocess.Popen') as spawn:
                with patch('sys.argv',['services.py','stop']):module.main()
                self.assertTrue((root/'var/services.paused').exists())
                with patch('sys.argv',['services.py','start','--internal']):module.main()
                spawn.assert_not_called()
    def test_user_launch_agent_has_no_credentials_or_system_daemon(self):
        module=load('login_service');value=module.definition(Path('/example/project'),'/usr/bin/python3')
        self.assertEqual(value['WorkingDirectory'],'/example/project')
        self.assertEqual(value['Umask'],63)
        self.assertEqual(value['ThrottleInterval'],30)
        self.assertNotIn('token',str(value).lower())
        self.assertTrue(value['KeepAlive'])
        self.assertEqual(value['ProgramArguments'][1],'/example/project/scripts/supervise.py')


if __name__=='__main__':unittest.main()
