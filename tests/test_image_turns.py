import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from dafeiyu.core import Fish
from dafeiyu.channel import inbound,tables
from dafeiyu.conversation import step
from test_media import png


class Vision:
    ready=True
    def __init__(self):self.calls=[]
    def plan(self,messages,images=None):self.calls.append((messages,images));return {'action':'reply','reply':'本鱼收到这张图了。','argument':''}


class ImageTurns(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.now=1793930400;self.model=Vision();self.f=Fish(self.tmp.name,self.model,clock=lambda:self.now);tables(self.f)
        with self.f.db:self.f.db.execute("INSERT INTO channel_binding VALUES (1,'a','s',0)")
        self.root=self.f.home;self.image=self.root/'gateway/media/inbound/one.png';self.image.parent.mkdir(parents=True);self.image.write_bytes(png())
    def tearDown(self):self.f.close();self.tmp.cleanup()
    def event(self,id,text,media=None):return dict(channel='openclaw-weixin',account='a',sender='s',message_id=id,group=False,text=text,media=media or [],buffer_text=True)
    def upload(self,id='one'):
        reply=inbound(self.f,self.event(id,'看这张图',[{'path':str(self.image),'mime':'image/png'}]))
        for p in (self.root/'media/conversation-inputs').iterdir():os.utime(p,(self.now,self.now))
        return reply
    def send(self,*args,**kwargs):return subprocess.CompletedProcess('send',0,'{}','')
    def test_image_and_following_text_use_one_vision_turn(self):
        self.assertEqual(self.upload(),'');self.now+=.5;inbound(self.f,self.event('two','主要看看右边'))
        self.assertEqual(self.model.calls,[]);self.now+=2
        self.assertEqual(step(self.f,self.send),'accepted');self.assertEqual(len(self.model.calls),1)
        self.assertIn('主要看看右边',self.model.calls[0][0][-1]['content']);self.assertEqual(len(self.model.calls[0][1]),1)
        self.assertTrue(self.image.exists())
    def test_recent_image_followup_reuses_actual_image_and_clear_removes_private_copy(self):
        self.upload();self.now+=2;step(self.f,self.send)
        cached=Path(self.model.calls[0][1][0]);self.assertTrue(cached.exists())
        self.now+=2;inbound(self.f,self.event('two','那张图旁边是什么？'));self.now+=2;step(self.f,self.send)
        self.assertEqual(self.model.calls[1][1],[str(cached)])
        self.f.command('/clear');self.assertFalse(cached.exists());self.assertTrue(self.image.exists())
    def test_unbound_media_cannot_be_opened_or_staged(self):
        with self.f.db:self.f.db.execute('DELETE FROM channel_binding')
        with patch('dafeiyu.media.store_images',side_effect=AssertionError('read before binding')):
            result=inbound(self.f,self.event('one','看图片',[{'path':'/etc/passwd','mime':'image/png'}]))
        self.assertIn('绑定',result)
    def test_preexisting_overflow_is_processed_in_batches_not_cancelled_as_new_input(self):
        for n in range(13):inbound(self.f,self.event(str(n),'一条连续文字'))
        self.now+=2
        self.assertEqual(step(self.f,self.send),'accepted')
        self.now+=2;self.assertEqual(step(self.f,self.send),'accepted');self.assertEqual(len(self.model.calls),2)

    def test_deployment_refuses_older_code_while_image_turn_is_pending(self):
        import importlib.util,sqlite3
        from unittest.mock import Mock
        root_code=Path(__file__).resolve().parent.parent
        spec=importlib.util.spec_from_file_location('deploy_image_fixture',root_code/'scripts/deploy.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'var').mkdir();release=root/'old-release';release.mkdir()
            db=sqlite3.connect(root/'var/fish.sqlite');db.execute('CREATE TABLE tasks(state TEXT)');db.execute('CREATE TABLE conversation_inbox(state TEXT,images TEXT)')
            db.execute('INSERT INTO conversation_inbox VALUES (?,?)',('queued','["private-copy.png"]'));db.commit();db.close()
            service=Mock()
            with patch.object(module,'ROOT',root),patch.object(module,'verify',return_value=release),patch.object(module,'module',return_value=service):
                with self.assertRaisesRegex(ValueError,'图片话轮'):module.activate('fixture')
            service.control.assert_not_called()
