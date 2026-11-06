import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from dafeiyu.speech import transcribe
from dafeiyu.video import analyze
from test_speech import wav

class Language(unittest.TestCase):
    def test_video_auto_language_and_default_chinese_are_explicit(self):
        calls=[]
        def runner(command,**kwargs):calls.append(command);return subprocess.CompletedProcess(command,0,json.dumps({'text':'A lunar orbit','language':'en'}),'')
        with patch('pathlib.Path.exists',return_value=True):
            self.assertEqual(transcribe('/private/fixture.wav',runner,language=None),'A lunar orbit')
            transcribe('/private/fixture.wav',runner)
        self.assertEqual(calls[0][-2:],['--language','auto']);self.assertEqual(calls[1][-2:],['--language','zh'])
    def test_unknown_language_is_reported_as_uncertain_not_usable_text(self):
        def runner(*a,**k):return subprocess.CompletedProcess('asr',0,json.dumps({'text':'hallucinated','uncertain_language':True}),'')
        with patch('pathlib.Path.exists',return_value=True):
            with self.assertRaisesRegex(ValueError,'不可靠'):transcribe('/private/fixture.wav',runner,language=None)
    def test_unsupported_language_setting_does_not_launch_process(self):
        with self.assertRaises(ValueError):transcribe('/private/fixture.wav',lambda *a,**k:self.fail('launched'),language='--other')
    def test_video_selects_auto_and_retains_scope(self):
        with tempfile.TemporaryDirectory() as home:
            root=Path(home).resolve();path=root/'media/video-inputs/test.mp4';path.parent.mkdir(parents=True);path.touch()
            out=root/'video-runs/test';out.mkdir(parents=True);(out/'audio.wav').write_bytes(wav())
            class Backend:
                def codex_reply(self,messages,**kwargs):self.messages=messages;return '只基于已提供画面回答。'
            model=Backend();decoded={'duration_seconds':1,'samples':[],'audio_file':'audio.wav','audio_seconds':1,'method':'sampled'}
            with patch('dafeiyu.video.decode',return_value=decoded),patch('dafeiyu.speech.transcribe',return_value='A lunar orbit') as asr:
                report,meta=analyze(model,{'path':str(path)},root,'test')
            self.assertIsNone(asr.call_args.kwargs['language']);self.assertIn('自动识别语言',report);self.assertIn('A lunar orbit',str(model.messages))
