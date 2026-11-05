import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from dafeiyu.core import Fish
from dafeiyu.channel import inbound,tables
from dafeiyu.media import store_video,MediaError
from dafeiyu.video import analyze,decode,VideoError


class Vision:
    ready=True
    def __init__(self):self.images=[]
    def codex_reply(self,messages,**kwargs):self.images=kwargs.get('images',[]);return '采样画面显示蓝色。'


class VideoTests(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name).resolve()
    def tearDown(self):self.tmp.cleanup()
    def fixture_path(self):
        p=self.root/'gateway/media/inbound/clip.mp4';p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'\0\0\0\x18ftypisom'+b'\0'*32);return p
    def fish(self):
        f=Fish(self.root,Vision());tables(f)
        with f.db:f.db.execute('INSERT INTO channel_binding VALUES (1,?,?,?)',('a','s',0))
        self.addCleanup(f.close);return f
    def test_video_upload_is_durable_task_not_claim_of_completed_viewing(self):
        f=self.fish();p=self.fixture_path()
        result=inbound(f,dict(channel='openclaw-weixin',account='a',sender='s',message_id='m',group=False,text='[视频]',media=[{'path':str(p),'mime':'video/mp4'}]))
        self.assertIn('已入队',result);task=f.command('/tasks')[0];self.assertEqual(task['kind'],'video');self.assertEqual(task['state'],'queued')
        payload=json.loads(task['goal']);self.assertTrue(Path(payload['path']).is_file());self.assertTrue(p.exists())
    def test_outside_and_symlink_and_nonvideo_refused(self):
        p=self.fixture_path();outside=self.root/'outside.mp4';outside.write_bytes(p.read_bytes())
        link=p.parent/'link.mp4';link.symlink_to(outside)
        for candidate in [outside,link]:
            with self.assertRaises(MediaError):store_video(self.root,[{'path':str(candidate)}])
        p.write_bytes(b'not a movie')
        with self.assertRaises(MediaError):store_video(self.root,[{'path':str(p)}])
    def test_quota_failure_does_not_leave_extra_input_copy(self):
        f=self.fish();p=self.fixture_path()
        with patch.object(f,'enqueue',side_effect=ValueError('任务预算已满')):
            reply=inbound(f,dict(channel='openclaw-weixin',account='a',sender='s',message_id='m',group=False,text='[视频]',media=[{'path':str(p),'mime':'video/mp4'}]))
        self.assertIn('预算',reply);self.assertEqual(list((self.root/'media/video-inputs').iterdir()),[])
    def test_analysis_reports_sampling_and_does_not_invent_audio(self):
        from test_media import png
        p=self.fixture_path();stored=store_video(self.root,[{'path':str(p)}]);out=self.root/'video-runs/id';out.mkdir(parents=True)
        image=out/'frame-0.png';image.write_bytes(png())
        metadata={'duration_seconds':3,'samples':[{'path':str(image),'file':'frame-0.png','seconds':0,'requested_seconds':0}],'audio_file':None,'audio_seconds':0,'method':'sampled'}
        model=Vision()
        with patch('dafeiyu.video.decode',return_value=metadata):report,result=analyze(model,{'path':str(stored)},self.root,'id')
        self.assertIn('1 张采样画面',report);self.assertIn('没有可用音轨',report);self.assertEqual(result['transcript'],'');self.assertEqual(model.images,[str(image)])
    def test_unknown_future_task_never_becomes_a_draft(self):
        f=self.fish()
        with f.db:f.db.execute("INSERT INTO tasks(id,kind,goal,state,due,created) VALUES ('unknown','future-kind','x','queued',?,?)",(f.clock(),f.clock()))
        f.tick();self.assertEqual(f.command('/tasks')[0]['state'],'failed');self.assertIn('不支持',f.command('/tasks')[0]['error'])
    @unittest.skipUnless(os.environ.get('DAFEIYU_TEST_VIDEO')=='1','optional pinned codec image')
    def test_real_networkless_decode_of_original_fixture(self):
        import dafeiyu.video as module
        from video_fixture import create_clip
        p=create_clip(self.root/'fixture',module.RUNTIME)
        result=decode(p,self.root/'decoded')
        self.assertEqual(result['duration_seconds'],3);self.assertEqual(len(result['samples']),4)
        self.assertEqual(result['samples'][0]['seconds'],0)
        self.assertTrue(all(Path(item['path']).is_file() for item in result['samples']))

    @unittest.skipUnless(os.environ.get('DAFEIYU_TEST_VIDEO')=='1','optional pinned codec image')
    def test_real_aac_extracts_bounded_mono_pcm(self):
        import wave
        import dafeiyu.video as module
        from video_fixture import create_clip
        p=create_clip(self.root/'fixture',module.RUNTIME,audio=True)
        result=decode(p,self.root/'decoded')
        self.assertEqual(result['audio_file'],'audio.wav')
        self.assertGreater(result['audio_seconds'],2.9)
        self.assertLess(result['audio_seconds'],3.2)
        with wave.open(str(self.root/'decoded/audio.wav')) as audio:
            self.assertEqual((audio.getnchannels(),audio.getsampwidth(),audio.getframerate()),(1,2,16000))
            self.assertTrue(any(audio.readframes(audio.getnframes())))
