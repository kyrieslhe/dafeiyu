import json
from pathlib import Path
import socket
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from dafeiyu.core import Fish
from dafeiyu.channel import inbound,tables
from dafeiyu.delivery import deliver
from dafeiyu.research import target,ResearchError,research,Text
from dafeiyu.coding import safe_relative,snapshot,apply,CodingError,digest


class Dummy:
    ready=True
    calls=0
    def reply(self,messages):self.calls+=1;return '回复'


class ConnectedTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.now=1793854800.0
        self.fish=Fish(self.tmp.name,Dummy(),lambda:self.now);tables(self.fish)
    def tearDown(self):self.fish.close();self.tmp.cleanup()
    def event(self,**changes):
        value=dict(channel='openclaw-weixin',account='a',sender='s',message_id='m',text='/remember 喜欢鱼',group=False);value.update(changes);return value
    def bind(self):
        with self.fish.db:self.fish.db.execute('INSERT INTO channel_binding VALUES (1,?,?,?)',('a','s',self.now))
    def task(self):
        identifier=self.fish.enqueue('reminder','喝水');self.fish.tick();return identifier
    def test_unbound_and_foreign_user_no_access(self):
        inbound(self.fish,self.event())
        self.assertEqual(self.fish.command('/memories'),[])
        self.bind();inbound(self.fish,self.event(sender='attacker'))
        self.assertEqual(self.fish.command('/memories'),[])
        self.assertEqual(self.fish.model.calls,0)
    def test_duplicate_and_group_rejected(self):
        self.bind();inbound(self.fish,self.event(group=True))
        self.assertEqual(self.fish.command('/memories'),[])
        inbound(self.fish,self.event());inbound(self.fish,self.event(text='/remember 不应该保存'))
        self.assertEqual(len(self.fish.command('/memories')),1)
    def test_interrupted_inbound_is_explicit_and_never_replayed(self):
        self.bind();event=self.event();key=json.dumps([event['account'],event['sender'],event['message_id']])
        with self.fish.db:self.fish.db.execute("INSERT INTO inbound VALUES (?,'running',NULL,?)",(key,self.now-200))
        reply=inbound(self.fish,event)
        self.assertIn('已中断',reply)
        self.assertEqual(self.fish.command('/memories'),[])
        self.assertEqual(self.fish.model.calls,0)

    def test_missing_provider_id_rejected(self):
        self.bind();inbound(self.fish,self.event(message_id=None))
        self.assertEqual(self.fish.command('/memories'),[])
    def test_timeout_not_blind_retried(self):
        self.bind();self.task()
        def timeout(*a,**kw):raise subprocess.TimeoutExpired('send',60)
        self.assertEqual(deliver(self.fish,timeout),'delivery_unknown')
        self.assertIsNone(deliver(self.fish,lambda *a,**k:self.fail('repeated')))
    def test_expired_context_waits_for_new_inbound(self):
        self.bind();self.task();self.now+=100
        self.assertEqual(deliver(self.fish),'waiting_context')
        self.assertIsNone(deliver(self.fish))
        self.now+=1
        inbound(self.fish,self.event(text='/tasks'))
        self.assertEqual(deliver(self.fish,lambda *a,**k:subprocess.CompletedProcess('send',0,'{}','')),'accepted')
        self.assertIsNone(deliver(self.fish))
    def test_pause_stops_delivery(self):
        self.bind();self.task();self.fish.command('/pause')
        self.assertIsNone(deliver(self.fish,lambda *a,**k:self.fail('sent while paused')))
    def test_research_private_addresses_rejected(self):
        for url in ['http://example.com','https://user:secret@example.com','https://example.com:444']:
            with self.assertRaises(ResearchError):target(url)
        with patch('socket.getaddrinfo',return_value=[(socket.AF_INET,socket.SOCK_STREAM,6,'',('127.0.0.1',443))]):
            with self.assertRaises(ResearchError):target('https://example.com')
    def test_research_mixed_dns_rejected(self):
        addresses=[(socket.AF_INET,socket.SOCK_STREAM,6,'',(ip,443)) for ip in ['8.8.8.8','169.254.169.254']]
        with patch('socket.getaddrinfo',return_value=addresses):
            with self.assertRaises(ResearchError):target('https://example.com')
    def test_no_sources_no_fake_report(self):
        with patch('dafeiyu.research.fetch',side_effect=ResearchError('失败')):
            with self.assertRaises(ResearchError):research(Dummy(),'查 https://example.com')
    def test_html_script_excluded(self):
        parser=Text();parser.feed('<p>真实正文</p><script>泄露秘密</script>')
        self.assertEqual(parser.parts,['真实正文'])
    def test_path_and_symlink_escape(self):
        for name in ['/tmp/a','../a','a/../b','.env','a/.git/config','a\\b']:
            with self.assertRaises(CodingError):safe_relative(name)
        project=Path(self.tmp.name)/'project';project.mkdir();(project/'escape').symlink_to('/tmp')
        with self.assertRaises(CodingError):snapshot(project)
    def test_stale_project_rejected_before_apply(self):
        root=Path(self.tmp.name)/'projects';project=root/'hello';project.mkdir(parents=True)
        (project/'hello.py').write_text('changed')
        payload={'project':'hello','original_hashes':{'hello.py':digest(b'original')},'files':{'hello.py':'new'}}
        with self.assertRaises(CodingError):apply(root,payload)
        self.assertEqual((project/'hello.py').read_text(),'changed')
    def approval(self,expires=None):
        identifier=self.fish.enqueue('code','{}')
        payload={'project':'hello','original_hashes':{},'files':{'hello.py':'new'}}
        value=digest(json.dumps(payload,sort_keys=True,ensure_ascii=False).encode())
        with self.fish.db:
            self.fish.db.execute("UPDATE tasks SET state='waiting_approval' WHERE id=?",(identifier,))
            self.fish.db.execute('INSERT INTO approvals VALUES (?,?,?,?,0)',(identifier,value,json.dumps(payload),expires or self.now+300))
        return identifier,value
    def test_expired_wrong_and_cancelled_approval(self):
        identifier,value=self.approval(self.now-1)
        with self.assertRaises(ValueError):self.fish.command('/approve '+identifier+' '+value)
        identifier,value=self.approval()
        with self.assertRaises(ValueError):self.fish.command('/approve '+identifier+' wrong')
        self.fish.command('/cancel '+identifier)
        with self.assertRaises(ValueError):self.fish.command('/approve '+identifier+' '+value)
    def test_approval_once(self):
        identifier,value=self.approval()
        with patch('dafeiyu.coding.apply',return_value='done') as application:
            self.assertEqual(self.fish.command('/approve '+identifier+' '+value),'done')
            with self.assertRaises(ValueError):self.fish.command('/approve '+identifier+' '+value)
            application.assert_called_once()


if __name__=='__main__':unittest.main()
