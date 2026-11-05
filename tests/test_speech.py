import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import wave
from dafeiyu.core import Fish
from dafeiyu.channel import inbound,tables
from dafeiyu.media import staged_audio,MediaError
from dafeiyu.speech import synthesize,transcribe


class Planner:
    ready=True
    def plan(self,messages,images=None):return {'action':'remember','argument':'我喜欢鱼','reply':'记住了'}


def wav(duration=1):
    out=io.BytesIO()
    with wave.open(out,'wb') as f:f.setnchannels(1);f.setsampwidth(2);f.setframerate(16000);f.writeframes(b'\0\0'*16000*duration)
    return out.getvalue()


class SpeechTests(unittest.TestCase):
    def test_audio_custody_rejects_long_or_raw_silk_and_cleans_copy(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d).resolve();p=root/'gateway/media/inbound/v.wav';p.parent.mkdir(parents=True)
            p.write_bytes(wav())
            with staged_audio(root,[{'path':str(p)}]) as staged:self.assertTrue(Path(staged).exists())
            self.assertFalse(Path(staged).exists());self.assertTrue(p.exists())
            for data in [b'#!SILK_V3',wav(61)]:
                p.write_bytes(data)
                with self.assertRaises(MediaError):
                    with staged_audio(root,[{'path':str(p)}]):self.fail('admitted unsupported audio')
    def test_transcription_cannot_write_memory_without_text_confirmation(self):
        with tempfile.TemporaryDirectory() as d:
            f=Fish(d,Planner());self.addCleanup(f.close);tables(f)
            p=f.home/'gateway/media/inbound/v.wav';p.parent.mkdir(parents=True);p.write_bytes(wav())
            with f.db:f.db.execute('INSERT INTO channel_binding VALUES (1,?,?,?)',('a','s',0))
            event=dict(channel='openclaw-weixin',account='a',sender='s',message_id='m',group=False,text='[语音]',media=[{'path':str(p),'mime':'audio/wav'}])
            with patch('dafeiyu.speech.transcribe',return_value='记住我喜欢鱼'):
                result=inbound(f,event)
            self.assertIn('文字确认',result);self.assertEqual(f.command('/memories'),[])
    def test_asr_subprocess_is_offline_and_does_not_inherit_credentials(self):
        with patch('pathlib.Path.exists',return_value=True):
            calls=[]
            def runner(command,**kwargs):calls.append(kwargs);return subprocess.CompletedProcess(command,0,json.dumps({'text':'你好'}),'')
            self.assertEqual(transcribe('/private/test.wav',runner),'你好')
        self.assertEqual(calls[0]['env']['HF_HUB_OFFLINE'],'1');self.assertEqual(calls[0]['timeout'],35)
        self.assertNotIn('DAFEIYU_API_KEY',calls[0]['env'])
    def test_no_paid_fallback_when_speech_runtime_missing(self):
        with patch('pathlib.Path.exists',return_value=False):
            with self.assertRaisesRegex(ValueError,'尚未安装'):transcribe('/private/test.wav')
    def test_tts_failure_removes_partial_audio(self):
        with tempfile.TemporaryDirectory() as d,patch('dafeiyu.speech.sys.platform','darwin'):
            def runner(command,**kwargs):
                if command[0].endswith('afconvert'):
                    Path(command[-1]).write_bytes(b'partial');return subprocess.CompletedProcess(command,1)
                return subprocess.CompletedProcess(command,0)
            with self.assertRaisesRegex(ValueError,'生成失败'):synthesize(d,'你好',runner)
            self.assertEqual(list((Path(d)/'media/outbound').glob('*.wav')),[])
    def test_unrequested_natural_speech_action_is_not_admitted(self):
        with tempfile.TemporaryDirectory() as d:
            f=Fish(d);self.addCleanup(f.close)
            class Speak:
                ready=True
                def plan(self,messages):return {'action':'speak','argument':'你好','reply':'我说给你听'}
            f.model=Speak();self.assertIn('没有创建',f.chat('你好'))
            self.assertEqual(f.command('/tasks'),[])
    def test_audio_asset_is_sent_only_to_owner_once(self):
        from dafeiyu.delivery import deliver
        with tempfile.TemporaryDirectory() as d:
            f=Fish(d,clock=lambda:1793854800.0);self.addCleanup(f.close);tables(f)
            with f.db:f.db.execute('INSERT INTO channel_binding VALUES (1,?,?,?)',('a','s',f.clock()))
            p=f.home/'media/outbound'/('a'*32+'.wav');p.parent.mkdir(parents=True);p.write_bytes(wav())
            key=f.enqueue('speech','你好')
            with patch('dafeiyu.speech.synthesize',return_value=p):f.tick()
            commands=[]
            def send(command,**kwargs):commands.append(command);return subprocess.CompletedProcess(command,0,'{}','')
            self.assertEqual(deliver(f,send),'accepted');self.assertIsNone(deliver(f,send))
            self.assertEqual(commands[0][commands[0].index('--media')+1],str(p))
            self.assertEqual(commands[0][commands[0].index('--target')+1],'s')
    def test_missing_audio_is_not_sent_as_success(self):
        from dafeiyu.delivery import deliver
        with tempfile.TemporaryDirectory() as d:
            f=Fish(d,clock=lambda:1793854800.0);self.addCleanup(f.close);tables(f)
            with f.db:
                f.db.execute('INSERT INTO channel_binding VALUES (1,?,?,?)',('a','s',f.clock()))
                key=f.enqueue('speech','你好')
                f.db.execute("UPDATE tasks SET state='succeeded' WHERE id=?",(key,))
                f.db.execute('INSERT INTO outbox(task_id,content) VALUES (?,?)',(key,'已生成音频'))
                f.db.execute('INSERT INTO task_assets VALUES (?,?,?)',(key,str(f.home/'outside.wav'),'audio/wav'))
            self.assertEqual(deliver(f,lambda *a,**k:self.fail('sent missing audio')),'asset_missing')
    def test_old_generated_audio_is_cleaned_without_touching_fresh_files(self):
        from dafeiyu.speech import cleanup
        with tempfile.TemporaryDirectory() as d:
            f=Fish(d);self.addCleanup(f.close);p=f.home/'media/outbound';p.mkdir(parents=True)
            old=p/('a'*32+'.wav');old.write_bytes(wav());fresh=p/('b'*32+'.wav');fresh.write_bytes(wav())
            os.utime(old,(f.clock()-8*86400,)*2);cleanup(f)
            self.assertFalse(old.exists());self.assertTrue(fresh.exists())
    @unittest.skipUnless(os.environ.get('DAFEIYU_TEST_SPEECH')=='1','optional installed macOS speech runtime')
    def test_real_local_tts_and_offline_asr(self):
        with tempfile.TemporaryDirectory() as d:
            p=synthesize(d,'你好，我是大肥鱼，今天也要开开心心。')
            self.assertGreater(p.stat().st_size,44)
            text=transcribe(str(p));self.assertGreater(len(text),5)
