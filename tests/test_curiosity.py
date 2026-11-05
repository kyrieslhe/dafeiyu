from datetime import datetime
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo
from dafeiyu.core import Fish,Model
from dafeiyu.curiosity import due,may_start,next_time,status
from dafeiyu.quota import summarize,guard


class Fake:
    ready=True
    def reply(self,messages):return 'test'


class CuriosityTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.now=datetime(2026,11,5,12,tzinfo=ZoneInfo('Asia/Hong_Kong')).timestamp()
        self.f=Fish(self.tmp.name,Fake(),lambda:self.now)
    def tearDown(self):self.f.close();self.tmp.cleanup()
    def schedule(self):
        self.f.command('/life random')
        with self.f.db:self.f.db.execute('UPDATE curiosity_policy SET next_due=?',(self.now-1,))
        due(self.f,self.now)
        return self.f.db.execute("SELECT * FROM tasks WHERE id LIKE 'curious-%'").fetchone()
    def test_random_is_opt_in_self_interests_and_persistent_without_backlog(self):
        due(self.f,self.now);self.assertEqual(self.f.command('/tasks'),[])
        row=self.schedule();due(self.f,self.now);self.assertTrue(row['id'].startswith('curious-'));self.assertEqual(len(self.f.command('/tasks')),1)
        self.assertEqual(len(self.f.command('/interest')),4);self.assertEqual(self.f.command('/memories'),[])
        self.assertTrue(self.f.db.execute('SELECT next_due FROM curiosity_policy').fetchone()[0]>self.now)
    def test_quota_unknown_or_low_defers_without_starting_or_spending_daily_budget(self):
        row=self.schedule()
        for state in ('low','unknown'):
            with self.f.db:self.assertFalse(may_start(self.f,row,self.now,{'status':state}))
        self.assertEqual(self.f.command('/tasks')[0]['state'],'queued');self.assertEqual(status(self.f)['started_today'],0)
    def test_actual_start_budget_four_and_night_reschedule(self):
        row=self.schedule()
        with self.f.db:
            for n in range(4):self.f.db.execute('INSERT INTO curiosity_runs VALUES (?,?,?,0)',('prior'+str(n),'2026-11-05',self.now))
            self.assertFalse(may_start(self.f,row,self.now,{'status':'ok'}))
        future=self.f.db.execute('SELECT due FROM tasks WHERE id=?',(row['id'],)).fetchone()[0]
        local=datetime.fromtimestamp(future,ZoneInfo('Asia/Hong_Kong'));self.assertEqual(local.day,6);self.assertEqual(local.hour,9)
        self.now=datetime(2026,11,6,23,tzinfo=ZoneInfo('Asia/Hong_Kong')).timestamp()
        with self.f.db:self.assertFalse(may_start(self.f,row,self.now,{'status':'low'}))
        self.assertEqual(datetime.fromtimestamp(self.f.db.execute('SELECT due FROM tasks WHERE id=?',(row['id'],)).fetchone()[0],ZoneInfo('Asia/Hong_Kong')).hour,9)
    def test_sharing_is_separate_from_four_discoveries_and_caps_at_two(self):
        from dafeiyu.curiosity import should_share
        with self.f.db:
            for n in range(3):self.f.db.execute('INSERT INTO curiosity_runs VALUES (?,?,?,0)',('curious-'+str(n),'2026-11-05',self.now))
            self.assertTrue(should_share(self.f,'curious-0','鲸鱼用半脑睡眠'))
            self.assertTrue(should_share(self.f,'curious-1','开源编译工具的新设计'))
            self.assertFalse(should_share(self.f,'curious-2','遥远行星的轨道'))
    def test_off_cancels_automatic_but_preserves_manual_tasks(self):
        row=self.schedule();manual=self.f.enqueue('reminder','喝水');self.f.command('/life off')
        states={r['id']:r['state'] for r in self.f.command('/tasks')}
        self.assertEqual(states[row['id']],'cancelled');self.assertEqual(states[manual],'queued')
    def test_quota_parser_prefers_codex_and_missing_is_unknown(self):
        value={'rateLimits':{'primary':{'usedPercent':99}},'rateLimitsByLimitId':{'codex':{'primary':{'usedPercent':30},'secondary':{'usedPercent':50}}}}
        self.assertEqual(summarize(value)['status'],'ok')
        value['rateLimitsByLimitId']['codex']['secondary']['usedPercent']=91
        self.assertEqual(summarize(value)['status'],'low')
        self.assertEqual(summarize({})['status'],'unknown')
        self.assertEqual(summarize({'rateLimits':{'primary':{'usedPercent':True}}})['status'],'unknown')
    def test_real_model_guard_cache_does_not_repeat_account_reads(self):
        self.f.model=Model();calls=[]
        def reader(_):calls.append(1);return {'status':'ok','remaining':{'primary':50,'secondary':60},'next_reset':None}
        self.assertEqual(guard(self.f,reader=reader)['status'],'ok');guard(self.f,reader=reader);self.assertEqual(len(calls),1)
        self.now+=61;guard(self.f,reader=reader);self.assertEqual(len(calls),2)
