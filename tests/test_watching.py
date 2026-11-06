import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from dafeiyu.core import Fish,Model,ModelError
from dafeiyu.public_video import resolve,cdn_url,_download
from dafeiyu.platforms import read
from dafeiyu.video import analyze,VideoError

URL='https://www.bilibili.com/video/BV1oBJo6GE22'
CDN='https://test.bilivideo.com/clip.mp4?temporary=private'

class Watching(unittest.TestCase):
    def test_resolution_requires_free_bounded_single_public_clip(self):
        view={'code':0,'data':{'duration':68,'cid':123,'pages':[{}],'rights':{},'title':'fixture'}}
        play={'code':0,'data':{'format':'mp4','timelength':68000,'durl':[{'size':100,'length':68000,'url':CDN}]}}
        def attempt(v,p):
            with patch('dafeiyu.research.fetch',side_effect=[{'text':json.dumps(v)},{'text':json.dumps(p)}]):return resolve(URL)
        self.assertEqual(attempt(view,play)['media_url'],CDN)
        for field,value in [('duration',121),('pages',[{},{}]),('rights',{'pay':1}),('is_upower_exclusive',True)]:
            v=copy.deepcopy(view);v['data'][field]=value
            with self.assertRaises(ModelError):attempt(v,play)
        for field,value in [('is_preview',True),('format','dash'),('timelength',121000),('durl',[{'size':21*1024*1024,'length':68000,'url':CDN}])]:
            p=copy.deepcopy(play);p['data'][field]=value
            with self.assertRaises(ModelError):attempt(view,p)
        for url in ['http://test.bilivideo.com/x','https://bilivideo.com.evil.test/x','https://user@a.bilivideo.com/x','https://127.0.0.1/x']:
            with self.assertRaises(ModelError):cdn_url(url)
    def test_download_integrity_and_failure_cleanup(self):
        from urllib.parse import urlsplit
        body=b'\0\0\0\x18ftypisom'+b'0'*32
        class Response(io.BytesIO):
            status=200
            def getheader(self,key,default=None):return default
        class Connection:
            def __init__(self,*args):pass
            def request(self,*args,**kwargs):pass
            def getresponse(self):return Response(body)
            def close(self):pass
        with tempfile.TemporaryDirectory() as home,patch('dafeiyu.research.target',return_value=(urlsplit(CDN),'1.1.1.1')),patch('dafeiyu.research.PinnedHTTPS',Connection):
            name='a'*32+'.mp4';result=_download(CDN,home,name,len(body),URL)
            self.assertEqual(result['bytes'],len(body));path=Path(home)/'media/video-inputs'/name;path.unlink()
            for expected in (len(body)-1,len(body)+1):
                with self.assertRaises(ModelError):_download(CDN,home,name,expected,URL)
                self.assertFalse(path.exists())
    def test_auto_duplicates_and_text_fallback_never_recommend(self):
        class Backend:
            ready=True
            def codex_reply(self,*args,**kwargs):return 'fixture'
            def reply(self,*args):return '简介文字。'
        with tempfile.TemporaryDirectory() as home:
            f=Fish(home,Backend());self.addCleanup(f.close);f.command('/watch on')
            source={'url':URL,'text':'description','title':'fixture'}
            with patch('dafeiyu.watching.sampled',side_effect=ModelError('不可下载')),patch('dafeiyu.platforms.page_source',return_value=source):
                _,meta=read(f,'bilibili',URL,'curious-fixture');self.assertIs(meta['recommend'],False)
                _,meta=read(f,'bilibili',URL,'manual');self.assertNotIn('recommend',meta)
            with f.db:f.db.execute('INSERT INTO video_choices VALUES (?,?,?,?,?,?,?,?)',(URL,'id','topic','title','sampled_clip',0,'reason',f.clock()))
            with patch('dafeiyu.watching.sampled') as sample:
                with self.assertRaises(ModelError):read(f,'bilibili',URL,'curious-next')
                sample.assert_not_called()
    def test_cancellation_prevents_model_launch(self):
        model=Model();model.cancelled=lambda:True
        with patch('dafeiyu.core.subprocess.Popen') as launch:
            with self.assertRaises(ModelError):model.codex_reply([])
            launch.assert_not_called()
    def test_judgment_is_strict_boolean_not_truthy_string(self):
        with tempfile.TemporaryDirectory() as home:
            home=Path(home).resolve();p=home/'media/video-inputs/test.mp4';p.parent.mkdir(parents=True);p.touch()
            class Backend:
                def codex_reply(self,*args,**kwargs):return self.output
            model=Backend();decoded={'duration_seconds':1,'samples':[],'method':'sampled'}
            with patch('dafeiyu.video.decode',return_value=decoded):
                for value in ('yes',1,None):
                    model.output=json.dumps({'report':'观察','recommend':value,'reason':'理由'})
                    with self.assertRaises(VideoError):analyze(model,{'path':str(p),'judge':True},home,'id')
                model.output=json.dumps({'report':'观察','recommend':False,'reason':'没有发现新内容'})
                _,meta=analyze(model,{'path':str(p),'judge':True},home,'id');self.assertIs(meta['recommend'],False)

    def test_negative_exploration_is_saved_without_notification(self):
        class Backend:
            ready=True
        with tempfile.TemporaryDirectory() as home:
            f=Fish(home,Backend());self.addCleanup(f.close)
            identifier=f.enqueue('explore','ocean')
            with patch('dafeiyu.research.research',return_value=('没有发现值得推荐的细节。',{'recommend':False,'sources':[]})):
                f.tick()
            self.assertEqual(f.db.execute('SELECT state FROM tasks WHERE id=?',(identifier,)).fetchone()[0],'succeeded')
            self.assertEqual(f.db.execute('SELECT count(*) FROM outbox WHERE task_id=?',(identifier,)).fetchone()[0],0)
