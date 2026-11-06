import subprocess
import tempfile
import unittest
from unittest.mock import patch
from dafeiyu.core import Fish
from dafeiyu.channel import tables,inbound
from dafeiyu.conversation import step
from test_speech import wav

class VoiceTurns(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.now=1793930400;self.calls=[];self.sent=[]
        parent=self
        class Backend:
            ready=True
            def plan(self,messages,images=None):
                parent.calls.append((messages,images));return {'action':'reply','argument':'','reply':'听到啦。\n\n你后面补充的本鱼也一起看到了。'}
        self.f=Fish(self.tmp.name,Backend(),lambda:self.now);tables(self.f)
        with self.f.db:self.f.db.execute("INSERT INTO channel_binding VALUES (1,'a','s',?)",(self.now,))
        self.voice=self.f.home/'gateway/media/inbound/voice.wav';self.voice.parent.mkdir(parents=True);self.voice.write_bytes(wav())
    def tearDown(self):self.f.close();self.tmp.cleanup()
    def receive(self,key,text,media=None):
        return inbound(self.f,dict(channel='openclaw-weixin',account='a',sender='s',message_id=key,group=False,text=text,media=media or [],buffer_text=True))
    def audio(self,key='voice'):
        return self.receive(key,'[语音]',[{'path':str(self.voice),'mime':'audio/wav'}])
    def send(self,cmd,**kwargs):self.sent.append(cmd[cmd.index('--message')+1]);return subprocess.CompletedProcess(cmd,0,'{}','')
    def test_voice_and_text_merge_once_without_retranscribing_duplicates(self):
        with patch('dafeiyu.speech.transcribe',return_value='今天跑步跑得好累') as asr:
            self.assertEqual(self.audio(),'');self.now+=.5;self.receive('text','不过感觉还挺开心的')
            self.audio();self.assertEqual(asr.call_count,1)
        self.assertEqual(self.calls,[]);self.now+=2
        self.assertEqual(step(self.f,self.send,sleep=lambda _:None),'accepted')
        self.assertEqual(len(self.calls),1);text=self.calls[0][0][-1]['content']
        self.assertIn('语音转写（可能有误）',text);self.assertIn('挺开心',text);self.assertEqual(len(self.sent),2)
        self.assertTrue(self.voice.exists())
    def test_voice_action_cannot_execute_even_when_burst_contains_text(self):
        def plan(*a,**k):return {'action':'remember','argument':'我喜欢鱼','reply':'记住了'}
        self.f.model.plan=plan
        with patch('dafeiyu.speech.transcribe',return_value='记住我喜欢鱼'):self.audio()
        self.receive('text','就是这句话');self.now+=2;step(self.f,self.send,sleep=lambda _:None)
        self.assertEqual(self.f.command('/memories'),[]);self.assertIn('文字确认',str(self.sent))
    def test_transcription_does_not_trigger_temporary_presence_controls(self):
        from dafeiyu.presence import status
        with patch('dafeiyu.speech.transcribe',return_value='我去睡觉了'):self.audio()
        self.assertEqual(status(self.f)['mode'],'available')
    def test_new_input_interrupts_voice_reply_without_repeating_asr(self):
        with patch('dafeiyu.speech.transcribe',return_value='我刚想到个事情'):self.audio()
        self.now+=2
        def sleep(_):self.receive('text','等一下，我改个说法')
        self.assertEqual(step(self.f,self.send,sleep),'interrupted');self.assertEqual(len(self.sent),1)
    def test_voice_with_image_uses_same_turn_without_allowing_actions(self):
        from test_media import png
        image=self.voice.parent/'pic.png';image.write_bytes(png())
        self.receive('image','看看这个',[{'path':str(image),'mime':'image/png'}]);self.now+=.2
        with patch('dafeiyu.speech.transcribe',return_value='这张图是什么颜色'):self.audio()
        self.now+=2;self.assertEqual(step(self.f,self.send,sleep=lambda _:None),'accepted')
        self.assertEqual(len(self.calls),1);self.assertEqual(len(self.calls[0][1]),1)
