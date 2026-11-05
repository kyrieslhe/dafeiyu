import base64
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from dafeiyu.browser import BrowserError,public_url,docker_command,render,browse
from dafeiyu.core import Fish

ROOT=Path(__file__).resolve().parent.parent


class Planner:
    ready=True
    def __init__(self,plans):self.plans=iter(plans)
    def codex_reply(self,*args,**kwargs):return json.dumps(next(self.plans))


def page(url='https://example.com',**changes):
    value=dict(url=url,title='Test',text='Observed page',links=[{'url':'https://example.com/next','text':'Next'}],partial=False,blocked_resources=[],screenshot='/private/test.png',retrieved_at='2026-11-05T00:00:00Z');value.update(changes);return value


class BrowserTests(unittest.TestCase):
    def test_no_file_http_userinfo_or_alternate_port(self):
        for url in ['file:///etc/passwd','http://example.com','https://u:p@example.com','https://example.com:444','https://example.com:bad']:
            with self.assertRaises(BrowserError):public_url(url)
    def test_container_has_no_network_credentials_or_privileged_caps(self):
        command=docker_command('fish-test',Path('/private/output'),ROOT/'integrations/browser')
        self.assertIn('--network=none',command);self.assertIn('--read-only',command);self.assertIn('--cap-drop=ALL',command)
        self.assertEqual(command[command.index('--user')+1],'pwuser');self.assertIn('--cap-add=SYS_CHROOT',command)
        self.assertNotIn('--privileged',command);self.assertNotIn('--ipc=host',command)
        self.assertFalse(any('SYS_ADMIN' in value or '.codex' in value or 'docker.sock' in value for value in command))
    def test_unknown_links_are_rejected_without_navigation(self):
        with patch('dafeiyu.browser.render',return_value=page()) as visit:
            with self.assertRaises(BrowserError):browse(Planner([{'action':'follow','link_index':99,'answer':''}]),'https://example.com 查看','/private','test')
            self.assertEqual(visit.call_count,1)
    def test_only_observed_link_navigation_and_actual_source_urls(self):
        plan=Planner([{'action':'follow','link_index':0,'answer':''},{'action':'done','link_index':-1,'answer':'结论 [伪造](https://other.example)'}])
        with patch('dafeiyu.browser.render',side_effect=[page(),page('https://example.com/next')]) as visit:
            report,metadata=browse(plan,'https://example.com 查看下一页','/private','test')
        self.assertEqual(visit.call_args_list[1].args[0],'https://example.com/next');self.assertNotIn('https://other.example',report)
        self.assertTrue(metadata['complete']);self.assertEqual(len(metadata['pages']),2)
    def test_three_page_limit_is_not_reported_as_completed(self):
        plan=Planner([{'action':'follow','link_index':0,'answer':'继续'}]*3)
        with patch('dafeiyu.browser.render',return_value=page()):report,metadata=browse(plan,'https://example.com 查看','/private','test')
        self.assertFalse(metadata['complete']);self.assertIn('尚未完成',report)
    def test_browser_task_is_durable_without_fake_completion(self):
        with tempfile.TemporaryDirectory() as directory:
            f=Fish(directory);self.addCleanup(f.close)
            self.assertIn('已入队',f.command('/browse https://example.com 查看首页'))
            self.assertEqual(f.command('/tasks')[0]['state'],'queued')
    def test_network_broker_refuses_private_targets(self):
        from dafeiyu.browser_network import fetch
        from dafeiyu.research import ResearchError
        with self.assertRaises(ResearchError):fetch('https://127.0.0.1')
    @unittest.skipUnless(os.environ.get('DAFEIYU_TEST_BROWSER')=='1','optional pinned Docker browser runtime')
    def test_real_sandbox_render_with_offline_fixture_resources(self):
        data=b'<html><title>Fish fixture</title><body><h1>Actual browser</h1><a href="https://example.com/next">Next</a><script>document.body.dataset.ran="yes"</script></body></html>'
        def fixture(url):return {'ok':True,'status':200,'headers':{'content-type':'text/html'},'body':base64.b64encode(data).decode(),'size':len(data),'sha256':hashlib.sha256(data).hexdigest()}
        with tempfile.TemporaryDirectory() as directory:
            result=render('https://example.com',Path(directory)/'page',fetcher=fixture)
            self.assertEqual(result['title'],'Fish fixture');self.assertIn('Actual browser',result['text'])
            self.assertTrue(Path(result['screenshot']).is_file());self.assertTrue(result['resources'])
