import tempfile
import unittest
from unittest.mock import patch
from dafeiyu.core import Fish,ModelError
from dafeiyu.platforms import canonical,read,page_source

BILI='https://www.bilibili.com/video/BV1ns41137gg'
DOU='https://www.douyin.com/video/7579520490004352302'


class Platforms(unittest.TestCase):
    def test_only_public_entries_no_accounts_messages_or_host_escape(self):
        self.assertEqual(canonical('bilibili',BILI+'/?spm_id_from=tracking'),BILI)
        for url in ('https://www.bilibili.com/account','https://www.bilibili.com/message','https://www.bilibili.com.evil.test/video/BV1ns41137gg',BILI.replace('https','file'),'https://user:pass@www.bilibili.com/video/BV1ns41137gg'):
            with self.assertRaises(ValueError):canonical('bilibili',url)
        self.assertEqual(canonical('douyin',DOU),DOU)
    def test_read_is_grounded_in_metadata_and_never_claims_video_view(self):
        class Model:
            ready=True
            def reply(self,messages):self.messages=messages;return '本鱼读到简介提到了海洋。'
        with tempfile.TemporaryDirectory() as home:
            model=Model();f=Fish(home,model)
            source={'url':BILI,'title':'鲸声','text':'这是一段关于鲸鱼的公开简介。','method':'public_metadata_only','retrieved_at':'2026-11-06','sha256':'fixture'}
            with patch('dafeiyu.platforms.page_source',return_value=source):report,metadata=read(f,'bilibili',BILI,'fixture')
            self.assertFalse(metadata['complete_video_view']);self.assertIn('没有播放',str(model.messages));self.assertIn('没有看完视频',report)
            self.assertEqual(f.command('/platforms')['visits'][0]['state'],'read_text_only');f.close()
    def test_login_challenge_does_not_create_fake_read_history(self):
        with tempfile.TemporaryDirectory() as home:
            f=Fish(home)
            with patch('dafeiyu.platforms.page_source',side_effect=ModelError('需要验证')):
                with self.assertRaises(ModelError):read(f,'douyin',DOU,'fixture')
            self.assertEqual(f.command('/platforms')['visits'][0]['state'],'unavailable');f.close()
