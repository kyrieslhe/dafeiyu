import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit
from dafeiyu.core import Fish,ModelError
from dafeiyu.nasa_video import canonical,resolve,read,keyword
from dafeiyu.public_video import cdn_url,_download,MAX_BYTES

PAGE='https://images.nasa.gov/details/Example%20Video'
MEDIA='https://images-assets.nasa.gov/video/Example%20Video/Example%20Video~small.mp4'
ITEM={'data':[{'nasa_id':'Example Video','media_type':'video','title':'Example','description':'NASA description'}]}

class NasaVideo(unittest.TestCase):
    def test_official_catalogue_asset_upgrades_only_exact_host(self):
        data={'collection':{'items':[{'href':MEDIA.replace('https:','http:')}]}}
        with patch('dafeiyu.research.fetch',return_value={'text':json.dumps(data)}):
            info=resolve(ITEM)
        self.assertEqual(info['media_url'],MEDIA);self.assertEqual(info['page'],PAGE);self.assertIsNone(info['size'])
        for href in [MEDIA.replace('images-assets.nasa.gov','images-assets.nasa.gov.evil.test'),MEDIA.replace('~small.mp4','~orig.mp4'),MEDIA.replace('Example%20Video/','Other/')]:
            with patch('dafeiyu.research.fetch',return_value={'text':json.dumps({'collection':{'items':[{'href':href}]}})}):
                with self.assertRaises(ModelError):resolve(ITEM)
    def test_canonical_and_cdn_reject_credentials_ports_and_host_escape(self):
        self.assertEqual(canonical(PAGE),PAGE)
        for url in [PAGE.replace('images.nasa.gov','evil.test'),PAGE.replace('details/','details/..%2f'),PAGE.replace('https:','http:'),PAGE.replace('images.nasa.gov','user@images.nasa.gov')]:
            with self.assertRaises(ModelError):canonical(url)
        for url in [MEDIA.replace('https:','http:'),MEDIA.replace('/video/','/private/'),MEDIA.replace('images-assets.nasa.gov','images-assets.nasa.gov.evil.test')]:
            with self.assertRaises(ModelError):cdn_url(url,'nasa')
    def test_unknown_size_requires_bounded_content_length_and_integrity(self):
        body=b'\0\0\0\x18ftypisom'+b'0'*32;length=[str(len(body))]
        class Response(io.BytesIO):
            status=200
            def getheader(self,key,default=None):return length[0] if key=='Content-Length' else default
        class Connection:
            def __init__(self,*a):pass
            def request(self,*a,**k):pass
            def getresponse(self):return Response(body)
            def close(self):pass
        with tempfile.TemporaryDirectory() as home,patch('dafeiyu.research.target',return_value=(urlsplit(MEDIA),'1.1.1.1')),patch('dafeiyu.research.PinnedHTTPS',Connection):
            name='a'*32+'.mp4'
            self.assertEqual(_download(MEDIA,home,name,None,PAGE,'nasa')['bytes'],len(body))
            path=Path(home)/'media/video-inputs'/name;path.unlink()
            for value in [None,'bad','0',str(MAX_BYTES+1),str(len(body)+1)]:
                length[0]=value
                with self.assertRaises(ModelError):_download(MEDIA,home,name,None,PAGE,'nasa')
                self.assertFalse(path.exists())
    def test_catalogue_sampler_preserves_real_source_and_visits(self):
        with tempfile.TemporaryDirectory() as home:
            f=Fish(home);self.addCleanup(f.close);f.command('/watch on')
            with patch('dafeiyu.research.fetch',return_value={'text':json.dumps({'collection':{'items':[ITEM]}})}),patch('dafeiyu.nasa_video.resolve',return_value={'page':PAGE}),patch('dafeiyu.watching.sampled',return_value=('observed',{'recommend':True})) as sample:
                report,meta=read(f,'宇宙','manual')
            self.assertEqual(report,'observed');self.assertEqual(f.db.execute('SELECT site,state FROM platform_visits').fetchone()[0],'nasa')
            self.assertEqual(sample.call_args.kwargs['info']['page'],PAGE)
    def test_unavailable_or_disabled_does_not_claim_view(self):
        with tempfile.TemporaryDirectory() as home:
            f=Fish(home);self.addCleanup(f.close)
            with self.assertRaises(ModelError):read(f,'宇宙','manual')
            f.command('/watch on')
            with patch('dafeiyu.research.fetch',return_value={'text':'{"collection":{"items":[]}}'}):
                with self.assertRaises(ModelError):read(f,'宇宙','manual')
            self.assertEqual(f.db.execute('SELECT state FROM platform_visits').fetchone()[0],'sample_unavailable')
        self.assertIsNone(keyword('AI 与开源工具'))
    def test_automatic_science_choice_obeys_off_switch_and_cooldown(self):
        from dafeiyu.platforms import choose
        with tempfile.TemporaryDirectory() as home:
            f=Fish(home);self.addCleanup(f.close);f.command('/watch on')
            key=next('curious-test-'+str(n) for n in range(100) if sum(('curious-test-'+str(n)).encode())%12==0)
            with f.db:f.db.execute('INSERT INTO interest_steps VALUES (?,?,NULL)',(key,'宇宙与自然科学'))
            self.assertEqual(choose(f,key),'nasa')
            f.command('/platforms off');self.assertIsNone(choose(f,key));f.command('/platforms on')
            with f.db:f.db.execute('INSERT INTO platform_visits VALUES (NULL,?,?,?,?)',('nasa','','sample_unavailable',f.clock()))
            self.assertIsNone(choose(f,key))
    def test_natural_video_share_keeps_link_without_duplicating_full_diagnostics(self):
        with tempfile.TemporaryDirectory() as home:
            f=Fish(home);self.addCleanup(f.close)
            key=f.enqueue('explore','宇宙')
            with patch('dafeiyu.research.research',return_value=('完整分析和诊断',{'sources':[],'recommend':True,'share':'看这条轨道，好有趣！\n'+PAGE})):
                f.tick()
            notice=f.db.execute('SELECT content FROM outbox WHERE task_id=?',(key,)).fetchone()[0]
            self.assertIn(PAGE,notice);self.assertNotIn('完整分析',notice)
            self.assertIn('完整分析',f.command('/result '+key))
