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
    def test_os_permission_failure_rolls_back_and_restores_manual_services(self):
        import json,subprocess,sys
        module=load('login_service')
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)/'project';(root/'var').mkdir(parents=True)
            home=Path(directory)/'user';home.mkdir()
            commands=[]
            def run(command,**kwargs):
                commands.append(command)
                if command[:2]==['launchctl','bootstrap']:
                    (root/'var/service-supervisor.log').write_text('Operation not permitted')
                return subprocess.CompletedProcess(command,0,'{}','')
            with patch.object(module,'ROOT',root),patch.object(module.sys,'platform','darwin'),patch('pathlib.Path.home',return_value=home),patch('subprocess.run',side_effect=run),patch('sys.argv',['login_service.py','install']):
                with self.assertRaisesRegex(SystemExit,'已撤销登录项'):
                    module.main()
            self.assertFalse((home/'Library/LaunchAgents'/(module.LABEL+'.plist')).exists())
            self.assertEqual(commands[-1][-1],'start')

    def test_user_launch_agent_has_no_credentials_or_system_daemon(self):
        module=load('login_service');value=module.definition(Path('/example/project'),'/usr/bin/python3')
        self.assertEqual(value['WorkingDirectory'],'/example/project')
        self.assertEqual(value['Umask'],63)
        self.assertEqual(value['ThrottleInterval'],30)
        self.assertNotIn('token',str(value).lower())
        self.assertTrue(value['KeepAlive'])
        self.assertEqual(value['ProgramArguments'][1],'/example/project/scripts/supervise.py')


class SupervisorTests(unittest.TestCase):
    def test_three_failed_checks_before_repair_then_healthy_resets(self):
        policy=load('supervise').RecoveryPolicy()
        self.assertIsNone(policy.observe(True,False,True,0,0))
        self.assertIsNone(policy.observe(True,False,True,30,30))
        self.assertEqual(policy.observe(True,False,True,60,60),('restart','unhealthy'))
        self.assertIsNone(policy.observe(True,True,True,90,90))
        self.assertIsNone(policy.observe(True,False,True,120,120))
        self.assertIsNone(policy.observe(True,False,True,150,150))
        self.assertEqual(policy.observe(True,False,True,180,180),('restart','unhealthy'))

    def test_missing_process_and_bounded_repairs(self):
        policy=load('supervise').RecoveryPolicy()
        self.assertEqual(policy.observe(False,False,False,0,0),('start','missing-process'))
        self.assertIsNone(policy.observe(False,False,False,30,30))
        for now in (60,120):self.assertEqual(policy.observe(False,False,False,now,now)[0],'start')
        self.assertEqual(policy.observe(False,False,False,180,180),('pause','repair-budget'))
        self.assertEqual(policy.observe(False,False,False,721,721)[0],'start')

    def test_resume_gap_repairs_even_when_processes_still_alive(self):
        policy=load('supervise').RecoveryPolicy()
        self.assertIsNone(policy.observe(True,True,True,0,1000))
        self.assertEqual(policy.observe(True,True,True,30,1600),('restart','host-resume'))
        self.assertIsNone(policy.observe(True,True,True,60,1630))

    def test_ac_only_assertion_without_display_or_global_settings(self):
        self.assertEqual(load('supervise').awake_command(123),['/usr/bin/caffeinate','-s','-w','123'])

    def test_silent_channel_is_healthy_and_does_not_require_inbound(self):
        import json,subprocess
        module=load('supervise')
        body={'channelAccounts':{'openclaw-weixin':[{'enabled':True,'configured':True,'running':True,'lastInboundAt':0}]}}
        class Response:
            status=200
            def __enter__(self):return self
            def __exit__(self,*args):pass
        with patch.object(module.urllib.request,'urlopen',return_value=Response()),patch('subprocess.run',return_value=subprocess.CompletedProcess([],0,json.dumps(body),'')):
            self.assertEqual(module.probe(),(True,True))
        body['channelAccounts']['openclaw-weixin'][0]['running']=False
        with patch.object(module.urllib.request,'urlopen',return_value=Response()),patch('subprocess.run',return_value=subprocess.CompletedProcess([],0,json.dumps(body),'')):
            self.assertEqual(module.probe(),(True,False))

    def test_second_session_does_not_spawn_or_change_options(self):
        module=load('stay_online')
        with patch.object(module,'current',return_value={'keep_awake':True}),patch('subprocess.Popen') as spawn,patch('sys.stdout',new_callable=io.StringIO):
            module.control('start',True)
            with self.assertRaisesRegex(SystemExit,'选项不同'):module.control('start',False)
            spawn.assert_not_called()


if __name__=='__main__':unittest.main()
