import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from dafeiyu.core import Fish
from dafeiyu.memory import tokens,recall
from dafeiyu.life import record


class Model:
    ready=True
    calls=0
    def reply(self,messages):self.calls+=1;return '待确认建议：做事前先检查当前记录，避免重复。'


class MemoryLife(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.now=1793836800.0
        self.fish=Fish(self.tmp.name,Model(),lambda:self.now)
    def tearDown(self):self.fish.close();self.tmp.cleanup()
    def test_old_cjk_memory_recalled_beyond_recent_ten(self):
        self.fish.remember('我特别喜欢粤语歌曲')
        for n in range(30):self.now+=1;self.fish.remember('项目记录编号 '+str(n))
        result=self.fish.command('/recall 粤语歌曲')
        self.assertEqual(result[0]['content'],'我特别喜欢粤语歌曲')
        self.assertEqual(result[0]['reason'],'topic_match')
        self.assertEqual(self.fish.model.calls,0)
    def test_pinned_memory_and_budget(self):
        self.fish.remember('常驻偏好');self.fish.command('/pin 1')
        for n in range(20):self.fish.remember('填充 '+str(n))
        result=recall(self.fish,'完全无关的问题',budget=1000)
        self.assertEqual(result[0]['reason'],'pinned')
        self.assertLessEqual(sum(len(json.dumps(x,ensure_ascii=False).encode()) for x in result),1000)
    def test_fts_safe_query_and_unicode_normalization(self):
        self.fish.remember('我喜欢 Python 编程')
        self.assertEqual(self.fish.command('/recall ＰＹＴＨＯＮ " OR *')[0]['id'],1)
        self.assertIn('粤语',tokens('我喜欢粤语歌曲'))
    def test_delete_cleans_index_tombstones_and_derivatives(self):
        self.fish.remember('喜欢粤语');self.fish.chat('喜欢粤语')
        self.fish.command('/reflect');self.fish.tick()
        self.fish.forget(1)
        self.assertEqual(self.fish.rows('SELECT * FROM memory_fts'),[])
        self.assertEqual(self.fish.rows('SELECT * FROM reflections'),[])
        self.assertEqual(self.fish.rows('SELECT * FROM episodes'),[])
        self.assertEqual(self.fish.rows('SELECT * FROM recall_log'),[])
        self.assertEqual(len(self.fish.rows('SELECT * FROM memory_tombstones')),1)
    def test_explicit_readd_clears_tombstone(self):
        self.fish.remember('喜欢粤语');self.fish.forget(1);self.fish.remember('喜欢粤语')
        self.assertEqual(self.fish.rows('SELECT * FROM memory_tombstones'),[])
    def test_expired_memory_not_in_context(self):
        self.fish.remember('阶段状态')
        with self.fish.db:self.fish.db.execute('UPDATE memory_meta SET expires=?',(self.now-1,))
        self.assertNotIn('阶段状态',str(self.fish.context('继续')))
    def test_reflections_not_facts_until_confirmed(self):
        record(self.fish,'test','research','真实阅读并完成研究')
        self.fish.command('/reflect');self.fish.tick()
        self.assertEqual(self.fish.command('/memories'),[])
        candidate=self.fish.command('/reflections')[0]
        self.fish.command('/accept '+str(candidate['id']))
        self.assertEqual(len(self.fish.command('/memories')),1)
        self.assertEqual(self.fish.rows('SELECT kind FROM memory_meta')[0]['kind'],'experience')
        self.fish.command('/accept '+str(candidate['id']))
        self.assertEqual(len(self.fish.command('/memories')),1)
    def test_task_timeline_only_after_success_once(self):
        identifier=self.fish.enqueue('reminder','喝水');self.fish.tick();self.fish.tick()
        events=self.fish.command('/timeline')
        self.assertEqual(len(events),1);self.assertEqual(events[0]['source'],'task:'+identifier)
    def test_no_fake_timeline_on_cancel_or_failure(self):
        identifier=self.fish.enqueue('reminder','喝水');self.fish.command('/cancel '+identifier);self.fish.tick()
        self.assertEqual(self.fish.command('/timeline'),[])
        self.fish.command('/reflect');self.fish.tick()
        self.assertEqual(self.fish.command('/timeline'),[])
    def test_life_is_opt_in_with_budget_and_offline_dedupe(self):
        self.fish.tick();self.assertEqual(self.fish.command('/tasks'),[])
        self.fish.command('/interest 开源软件');self.fish.command('/life on 00:00')
        def fake(*args):return ('真实研究结果',{'sources':[]})
        with patch('dafeiyu.research.research',side_effect=fake):
            self.fish.tick();self.fish.tick()
            self.assertEqual(len(self.fish.command('/tasks')),1)
            self.now+=5*86400;self.fish.tick();self.fish.tick()
            self.assertEqual(len(self.fish.command('/tasks')),2)
        self.assertEqual(len(self.fish.command('/timeline')),2)
    def test_pause_and_life_off_stop_new_exploration(self):
        self.fish.command('/interest 科学');self.fish.command('/life on 00:00');self.fish.command('/pause')
        self.fish.tick();self.assertEqual(self.fish.command('/tasks'),[])
        self.fish.command('/life off');self.fish.command('/resume');self.fish.tick()
        self.assertEqual(self.fish.command('/tasks'),[])
    def test_no_secrets_in_memory_or_interests(self):
        for text in ['我的密码是 123456','api_key: super-secret-value']:
            with self.assertRaises(ValueError):self.fish.remember(text)
        with self.assertRaises(ValueError):self.fish.command('/interest 我的密码是 123456')
    def test_migration_existing_memories_and_restart(self):
        self.fish.remember('早期记忆');self.fish.close()
        self.fish=Fish(self.tmp.name,Model(),lambda:self.now)
        self.assertEqual(self.fish.command('/recall 早期记忆')[0]['content'],'早期记忆')
        self.assertEqual(len(self.fish.rows('SELECT * FROM memory_fts')),1)
    def test_forget_also_clears_derived_accepted_experience(self):
        self.fish.remember('原始偏好')
        from dafeiyu.memory import remember
        remember(self.fish,'从原始偏好推导的经验',kind='experience',source='reflection:1')
        self.fish.forget(1)
        self.assertEqual(self.fish.command('/memories'),[])

    def test_conversation_excerpt_retention_matches_raw_chat(self):
        record(self.fish,'chat:old','conversation','旧聊天摘录')
        record(self.fish,'task:old','research','已完成的真实研究')
        self.now+=31*86400
        self.fish.close();self.fish=Fish(self.tmp.name,Model(),lambda:self.now)
        events=self.fish.command('/timeline')
        self.assertEqual(len(events),1);self.assertEqual(events[0]['kind'],'research')
        self.assertIn('+08:00',events[0]['at'])

    def test_life_requires_interests_and_valid_time(self):
        with self.assertRaises(ValueError):self.fish.command('/life on 10:00')
        self.fish.command('/interest 科学')
        with self.assertRaises(ValueError):self.fish.command('/life on 25:00')


if __name__=='__main__':unittest.main()
