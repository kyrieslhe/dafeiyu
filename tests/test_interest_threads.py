import tempfile
import unittest
from unittest.mock import Mock
from dafeiyu.core import Fish
from dafeiyu.interests import plan,complete,context


class Threads(unittest.TestCase):
    def test_successful_discoveries_connect_but_questions_never_become_facts(self):
        with tempfile.TemporaryDirectory() as home:
            f=Fish(home);f.command('/interest 海洋');rng=Mock();rng.random.return_value=0
            with f.db:
                first=plan(f,'海洋','a',rng)
                self.assertNotIn('上一回',first)
                complete(f,'a','鲸鱼有不同的歌声。\n下次想知道：歌声如何传播？\n\n### 抓取记录\nsource')
                second=plan(f,'海洋','b',rng)
                self.assertIn('歌声如何传播',second);self.assertIn('上一回',second)
                complete(f,'b','传播依赖海洋条件。\n下次想知道：温度有什么影响？')
                plan(f,'海洋','c',rng);complete(f,'c','另一项来源。\n下次想知道：盐度呢？')
                fresh=plan(f,'海洋','d',rng)
                self.assertNotIn('上一回',fresh)
            self.assertEqual(f.command('/memories'),[]);self.assertEqual(context(f)[0]['depth'],3)
            f.command('/uninterest 1');self.assertEqual(context(f),[])
            with f.db:complete(f,'d','不能复活已移除的兴趣。\n下次想知道：什么？')
            self.assertEqual(context(f),[]);f.close()
    def test_failed_search_does_not_change_last_successful_thread(self):
        with tempfile.TemporaryDirectory() as home:
            f=Fish(home);f.command('/interest 星空');rng=Mock();rng.random.return_value=0
            with f.db:
                plan(f,'星空','a',rng);complete(f,'a','真实记录。\n下次想知道：另一个问题？')
                plan(f,'星空','failed',rng)
            self.assertEqual(context(f)[0]['last_task'],'a')
            self.assertEqual(f.command('/threads')[0]['last_task'],'a')
            f.close()
