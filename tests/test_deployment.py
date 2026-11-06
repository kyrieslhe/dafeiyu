import importlib.util
import json
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import unittest
from unittest.mock import Mock,patch
from dafeiyu.deployment import prepare,verify,selected,configure,write

ROOT=Path(__file__).resolve().parent.parent


class DeploymentTests(unittest.TestCase):
    def repo(self,root):
        subprocess.run(['git','init','-q',str(root)],check=True)
        def git(*args):return subprocess.check_output(['git',*args],cwd=root).decode().strip()
        git('config','user.email','fixture@example.invalid');git('config','user.name','Fixture')
        (root/'var').mkdir();(root/'var/private').write_text('never archive')
        (root/'.gitignore').write_text('var/\n');(root/'app.py').write_text('print(1)\n')
        git('add','.');git('commit','-qm','fixture');commit=git('rev-parse','HEAD');git('update-ref','refs/remotes/origin/main',commit)
        return commit
    def test_archive_excludes_private_files_and_detects_modified_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();commit=self.repo(root);release=prepare(root)
            self.assertEqual(selected(root),root)
            self.assertEqual((release/'var').resolve(),root/'var')
            receipt=json.loads((release/'release.json').read_text())
            self.assertNotIn('var/private',receipt['files'])
            write(root/'var/active-release.json',{'commit':commit})
            self.assertEqual(selected(root),release)
            (root/'app.py').write_text('print(2)')
            self.assertEqual((release/'app.py').read_text(),'print(1)\n')
            self.assertEqual(verify(root,commit),release)
            (release/'app.py').chmod(0o600);(release/'app.py').write_text('changed')
            with self.assertRaises(ValueError):selected(root)
    def test_prepare_refuses_unmerged_work(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();self.repo(root);(root/'app.py').write_text('changed')
            with self.assertRaises(ValueError):prepare(root)
    def test_config_only_changes_bridge_code_locations(self):
        config={'gateway':{'auth':{'token':'fixture-not-a-secret'}},'plugins':{'load':{'paths':['/app/integrations/openclaw','/app/var/tencent']},'entries':{'dafeiyu-bridge':{'config':{'project':'/app','home':'/app/var'}}}}}
        result=configure(config,Path('/app/var/releases/commit'),Path('/app'))
        self.assertEqual(result['gateway'],{'auth':{'token':'fixture-not-a-secret'}})
        self.assertEqual(result['plugins']['load']['paths'][1],'/app/var/tencent')
        self.assertEqual(result['plugins']['entries']['dafeiyu-bridge']['config']['home'],'/app/var')
    def test_failed_readiness_restores_previous_receipt_and_config(self):
        spec=importlib.util.spec_from_file_location('deploy_fixture',ROOT/'scripts/deploy.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();commit=self.repo(root);release=prepare(root)
            db=sqlite3.connect(root/'var/fish.sqlite');db.execute('CREATE TABLE tasks(state TEXT)');db.commit();db.close()
            config={'plugins':{'load':{'paths':[str(root/'integrations/openclaw')]},'entries':{'dafeiyu-bridge':{'config':{'project':str(root),'home':str(root/'var')}}}}}
            write(root/'var/gateway/openclaw.json',config)
            service=Mock();service.state.return_value={'gateway':{},'worker':{}};service.active.return_value=True
            supervisor=Mock();supervisor.probe.return_value=(False,False)
            with patch.object(module,'ROOT',root),patch.object(module,'module',side_effect=lambda name:service if name=='services' else supervisor),patch.object(module.time,'sleep'):
                with self.assertRaises(ValueError):module.activate(commit)
            self.assertEqual(json.loads((root/'var/gateway/openclaw.json').read_text()),config)
            self.assertFalse((root/'var/active-release.json').exists())
            self.assertEqual([call.args[0].action for call in service.control.call_args_list],['stop','start','stop','start'])
            db=sqlite3.connect(root/'var/fish.sqlite');db.execute("INSERT INTO tasks VALUES ('running')");db.commit();db.close();service.reset_mock()
            with patch.object(module,'ROOT',root),patch.object(module,'module',return_value=service):
                with self.assertRaisesRegex(ValueError,'任务运行'):module.activate(commit)
            service.control.assert_not_called()
