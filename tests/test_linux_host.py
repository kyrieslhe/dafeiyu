import importlib.util
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parent.parent


def load(name):
    spec=importlib.util.spec_from_file_location(name,ROOT/'scripts'/(name+'.py'));module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


class LinuxHost(unittest.TestCase):
    def test_runtime_distribution_and_architecture_are_explicit(self):
        module=load('setup_runtime')
        self.assertEqual(module.distribution('Linux','aarch64'),('linux','arm64'))
        self.assertEqual(module.distribution('Darwin','x86_64'),('darwin','x64'))
        for system,machine in [('Windows','AMD64'),('Linux','riscv64')]:
            with self.assertRaises(ValueError):module.distribution(system,machine)
    def test_user_service_quotes_paths_without_shell_or_credential_environment(self):
        module=load('linux_service');value=module.definition(Path('/example/fish % $ path'),'/usr/bin/python3',Path('/example/user'))
        self.assertIn('WorkingDirectory=/example/fish %% $ path',value);self.assertNotIn('WorkingDirectory="',value);self.assertIn('Type=exec',value);self.assertIn('%%',value);self.assertIn('UMask=0077',value);self.assertIn('$$',value)
        self.assertNotIn('sudo',value);self.assertNotIn('/bin/sh -c',value);self.assertNotIn('TOKEN',value)
        self.assertIn('WantedBy=default.target',value)
        with self.assertRaises(ValueError):module.quote('/example/bad\nExecStart=/bad')

    def test_health_observation_expires_and_never_exports_unknown_fields(self):
        import tempfile
        from dafeiyu.runtime_health import record,summary
        with tempfile.TemporaryDirectory() as home:
            record(home,{'sampled_at':1000,'processes_ok':True,'gateway_ok':True,'channel_ok':True,'token':'fixture-private'})
            self.assertTrue(summary(home,1030)['fresh']);self.assertFalse(summary(home,1201)['fresh'])
            self.assertNotIn('token',str(summary(home,1030)))
    def test_clear_blocks_automatic_task_context_reinjection_but_keeps_explicit_report(self):
        import tempfile
        from dafeiyu.core import Fish
        from dafeiyu.relationship import context
        with tempfile.TemporaryDirectory() as home:
            f=Fish(home,clock=lambda:1000)
            with f.db:f.db.execute("INSERT INTO tasks(id,kind,goal,state,result,created) VALUES ('old','research','old question','succeeded','old answer',999)")
            self.assertTrue(context(f,'刚才的任务')['最近任务实际状态（成功不等于送达）'])
            f.command('/clear')
            self.assertEqual(context(f,'刚才的任务')['最近任务实际状态（成功不等于送达）'],[])
            self.assertIn('old answer',f.command('/result old'));f.close()
