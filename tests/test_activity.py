from datetime import datetime
from zoneinfo import ZoneInfo
import tempfile
import unittest
from dafeiyu.core import Fish
from dafeiyu.activity import day

class Activity(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.now=datetime(2026,11,6,12,tzinfo=ZoneInfo('Asia/Hong_Kong')).timestamp();self.f=Fish(self.tmp.name,clock=lambda:self.now)
    def tearDown(self):self.f.close();self.tmp.cleanup()
    def note(self,key,created):
        with self.f.db:self.f.db.execute('INSERT INTO exploration_notes VALUES (?,?,?,?,?)',(key,'海洋','有来源的发现','[]',created))
    def test_today_is_hong_kong_day_and_does_not_include_old_or_future_records(self):
        self.note('today',self.now-60);self.note('old',self.now-86400);self.note('future',self.now+60)
        value=day(self.f);self.assertEqual(value['date'],'2026-11-06');self.assertEqual([row['task_id'] for row in value['completed_explorations']],['today'])
        self.assertIn('+08:00',value['completed_explorations'][0]['completed_at'])
    def test_started_failed_and_queued_are_not_completed_or_delivered(self):
        with self.f.db:
            self.f.db.execute("INSERT INTO tasks(id,kind,goal,state,created) VALUES ('curious-failed','explore','ocean','failed',?)",(self.now-10,))
            self.f.db.execute("INSERT INTO curiosity_runs VALUES ('curious-failed','2026-11-06',?,0)",(self.now-10,))
        self.f.enqueue('explore','pending')
        value=day(self.f);self.assertEqual(value['completed_explorations'],[]);self.assertEqual(value['channel_accepted_notices'],[])
        self.assertEqual(value['actual_random_starts'][0]['state'],'failed');self.assertEqual(value['queued_explorations'],1)
    def test_clear_removes_old_activity_background_and_empty_day_does_not_invent_events(self):
        self.note('old',self.now-60);self.assertTrue(day(self.f)['completed_explorations']);self.f.command('/clear')
        self.assertEqual(day(self.f)['completed_explorations'],[]);self.assertIn('不编造',day(self.f)['scope'])
        self.assertEqual(self.f.command('/day')['date'],'2026-11-06')
