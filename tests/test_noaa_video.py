import json
import tempfile
import unittest
from unittest.mock import patch
from dafeiyu.core import Fish,ModelError
from dafeiyu.noaa_video import canonical,resolve,read,DIRECTORY
from dafeiyu.public_video import cdn_url

PAGE='https://oceantoday.noaa.gov/animalsoftheice_belugawhale/'
SMALL=PAGE+'clip_sm.mp4'
LARGE=PAGE+'clip_large.mp4'
CDN='https://cdn.oceanservice.noaa.gov/oceantodayprod/media/animalsoftheice_belugawhale/clip_sm.mp4'
class NoaaVideo(unittest.TestCase):
    def test_official_page_chooses_small_clip_and_labels_unverified_archive_date(self):
        source={'url':PAGE,'title':'Beluga Whales','text':'Transcript\nOfficial narration','links':[LARGE,SMALL]}
        with patch('dafeiyu.research.fetch',return_value=source) as get:info=resolve(PAGE)
        self.assertEqual(info['media_url'],SMALL);self.assertEqual(info['source'],'noaa');self.assertIsNone(info['size'])
        self.assertTrue(get.call_args.kwargs['include_links']);self.assertIn('发布时间未核实',info['description'])
    def test_page_and_redirect_resources_reject_host_or_path_escape(self):
        self.assertEqual(canonical(PAGE),PAGE);self.assertEqual(cdn_url(CDN,'noaa'),CDN)
        for page in [PAGE.replace('oceantoday.noaa.gov','evil.test'),PAGE+'../../',PAGE.replace('https:','http:')]:
            with self.assertRaises(ModelError):canonical(page)
        for url in [CDN.replace('/oceantodayprod/media/','/other/'),CDN.replace('cdn.oceanservice.noaa.gov','cdn.oceanservice.noaa.gov.evil.test'),CDN.replace('https:','http:'),CDN.replace('clip_sm.mp4','../../clip.mp4')]:
            with self.assertRaises(ModelError):cdn_url(url,'noaa')
    def test_directory_sampling_records_actual_source_and_deduplicates_seen(self):
        with tempfile.TemporaryDirectory() as home:
            f=Fish(home);self.addCleanup(f.close);f.command('/watch on')
            directory={'url':DIRECTORY,'links':[PAGE,PAGE,'https://evil.test/clip/']}
            with f.db:
                f.db.execute('INSERT INTO interest_steps VALUES (?,?,NULL)',('curious-example','海洋与动物'))
                f.db.execute('INSERT INTO interest_steps VALUES (?,?,NULL)',('curious-next','海洋与动物'))
            with patch('dafeiyu.research.fetch',return_value=directory),patch('dafeiyu.noaa_video.resolve',return_value={'page':PAGE}),patch('dafeiyu.watching.sampled',return_value=('observed',{'recommend':True})):
                self.assertEqual(read(f,'海洋鲸鱼','curious-example')[0],'observed')
            self.assertEqual(f.db.execute('SELECT site FROM platform_visits').fetchone()[0],'noaa')
            with f.db:f.db.execute('INSERT INTO video_choices VALUES (?,?,?,?,?,?,?,?)',(PAGE,'id','海洋','鲸鱼','sampled_clip',1,'new',f.clock()))
            with patch('dafeiyu.research.fetch',return_value=directory),patch('dafeiyu.watching.sampled') as sample:
                with self.assertRaises(ModelError):read(f,'海洋鲸鱼','curious-next')
                sample.assert_not_called()
    def test_watch_and_platform_controls_apply_to_marine_discovery(self):
        from dafeiyu.platforms import choose
        with tempfile.TemporaryDirectory() as home:
            f=Fish(home);self.addCleanup(f.close)
            with self.assertRaises(ModelError):read(f,'海洋','manual')
            f.command('/watch on');key=next('curious-noaa-'+str(n) for n in range(100) if sum(('curious-noaa-'+str(n)).encode())%4==0)
            with f.db:f.db.execute('INSERT INTO interest_steps VALUES (?,?,NULL)',(key,'海洋与动物'))
            self.assertEqual(choose(f,key),'noaa');f.command('/platforms off');self.assertIsNone(choose(f,key))
    def test_unavailable_candidates_record_failure_without_claiming_view(self):
        with tempfile.TemporaryDirectory() as home:
            f=Fish(home);self.addCleanup(f.close);f.command('/watch on')
            with patch('dafeiyu.noaa_video.resolve',side_effect=ModelError('no public clip')):
                with self.assertRaises(ModelError):read(f,PAGE,'manual')
            self.assertEqual(f.db.execute('SELECT state FROM platform_visits').fetchone()[0],'sample_unavailable')
