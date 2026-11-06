import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from dafeiyu.core import Fish
from dafeiyu.channel import inbound,tables
from dafeiyu.conversation import step,bubbles
from dafeiyu.delivery import deliver


class Model:
    ready=True
    def __init__(self):self.calls=[]
    def reply(self,messages):self.calls.append(messages);return '先接住你的意思。\n\n再一起看看。'


class ConversationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.now=1793930400;self.model=Model();self.f=Fish(self.tmp.name,self.model,clock=lambda:self.now);tables(self.f)
        with self.f.db:self.f.db.execute('INSERT INTO channel_binding VALUES (1,?,?,?)',('account','sender',self.now))
        self.sent=[]
    def tearDown(self):self.f.close();self.tmp.cleanup()
    def receive(self,message,text):
        return inbound(self.f,dict(channel='openclaw-weixin',account='account',sender='sender',message_id=message,group=False,text=text,buffer_text=True))
    def send(self,command,**kwargs):self.sent.append(command[command.index('--message')+1]);return subprocess.CompletedProcess(command,0,'{}','')
    def test_serial_ingress_is_fast_and_burst_gets_one_model_call(self):
        self.assertEqual(self.receive('one','我想到个事'),'');self.now+=.5
        self.assertEqual(self.receive('two','再补充一点'),'');self.assertEqual(self.model.calls,[])
        self.assertIsNone(step(self.f,self.send));self.now+=2
        self.assertEqual(step(self.f,self.send,sleep=lambda _:None),'accepted')
        self.assertEqual(len(self.model.calls),1)
        self.assertEqual(self.model.calls[0][-1]['content'],'我想到个事\n再补充一点')
        self.assertEqual(self.sent,['先接住你的意思。','再一起看看。'])
        self.receive('two','再补充一点');self.assertIsNone(step(self.f,self.send));self.assertEqual(len(self.model.calls),1)
    def test_new_input_interrupts_remaining_bubbles(self):
        self.receive('one','你好');self.now+=2
        def sleep(_):self.receive('two','等等，我补充一下')
        self.assertEqual(step(self.f,self.send,sleep),'interrupted');self.assertEqual(len(self.sent),1)
        last=self.f.db.execute("SELECT content FROM messages WHERE role='assistant' ORDER BY id DESC LIMIT 1").fetchone()[0]
        self.assertNotIn('再一起看看',last)
    def test_new_input_during_generation_suppresses_stale_reply(self):
        self.receive('one','原来的话');self.now+=2
        original=self.model.reply
        def reply(messages):self.receive('two','新的补充');return original(messages)
        self.model.reply=reply
        self.assertEqual(step(self.f,self.send),'superseded');self.assertEqual(self.sent,[])
        self.assertEqual(self.f.db.execute("SELECT count(*) FROM messages WHERE role='assistant'").fetchone()[0],0)
    def test_management_commands_are_not_merged_with_chat(self):
        self.receive('one','/clear');self.receive('two','新话题');self.now+=2
        step(self.f,self.send,sleep=lambda _:None)
        self.assertEqual(self.model.calls,[])
        self.now+=2;step(self.f,self.send,sleep=lambda _:None)
        self.assertEqual(len(self.model.calls),1)
        self.assertEqual(self.model.calls[0][-1]['content'],'新话题')
    def test_uncertain_send_is_not_replayed(self):
        self.receive('one','你好');self.now+=2
        def fail(*a,**k):raise subprocess.TimeoutExpired('send',45)
        self.assertEqual(step(self.f,fail),'delivery_unknown');self.assertIsNone(step(self.f,self.send));self.assertEqual(self.sent,[])
    def test_proactive_send_does_not_require_recent_user_message(self):
        with self.f.db:
            self.f.db.execute("INSERT INTO tasks(id,kind,goal,state,result,created) VALUES ('discovery','explore','x','succeeded','真实发现',?)",(self.now,))
            self.f.db.execute("INSERT INTO outbox(task_id,content) VALUES ('discovery','真实发现')")
            self.f.db.execute('UPDATE channel_binding SET last_seen=?',(self.now-3600,))
        self.assertEqual(deliver(self.f,self.send),'accepted');self.assertEqual(len(self.sent),1)
    def test_semantic_bubbles_keep_code_and_long_answers_intact(self):
        self.assertEqual(bubbles('一段。\n\n另一段。'),['一段。','另一段。'])
        for text in ('```py\na=1\n```\n\n说明','a'*1000+'\n\nend','- 一项\n\n- 二项'):
            self.assertEqual(bubbles(text),[text])
