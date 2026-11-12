import tempfile
import unittest
from unittest.mock import Mock
from datetime import datetime
from dafeiyu.core import Fish, ModelError


class Reminders(unittest.TestCase):
    def setUp(self):
        self.home=tempfile.TemporaryDirectory();self.now=1794528000
        self.model=Mock(ready=True);self.model.cancelled=lambda:False
        self.fish=Fish(self.home.name,self.model,clock=lambda:self.now)

    def tearDown(self):self.fish.close();self.home.cleanup()

    def test_list_orders_actual_deadlines_and_excludes_finished_and_other_jobs(self):
        late=self.fish.enqueue('reminder','稍后的提醒',self.now+7200)
        early=self.fish.enqueue('reminder','较早的提醒',self.now+3600)
        other=self.fish.enqueue('research','研究');finished=self.fish.enqueue('reminder','已结束')
        with self.fish.db:self.fish.db.execute("UPDATE tasks SET state='succeeded' WHERE id=?",(finished,))
        result=self.fish.command('看看我的提醒')
        self.assertLess(result.index(early),result.index(late))
        self.assertNotIn(other,result);self.assertNotIn(finished,result)
        self.assertIn('香港时间',result);self.assertIn('不是已送达',result)
        self.model.plan.assert_not_called()

    def test_reschedule_persists_without_replacing_or_duplicating_reminder(self):
        key=self.fish.enqueue('reminder','归还图书',self.now+7200)
        self.assertIn('改好啦',self.fish.command('修改提醒 '+key+' 到 2026-12-01T09:00'))
        row=self.fish.db.execute('SELECT * FROM tasks WHERE id=?',(key,)).fetchone()
        self.assertEqual(row['due'],datetime.fromisoformat('2026-12-01T09:00:00+08:00').timestamp())
        self.assertEqual(row['goal'],'归还图书');self.assertEqual(row['state'],'queued')
        self.assertEqual(self.fish.db.execute('SELECT count(*) FROM tasks').fetchone()[0],1)
        self.fish.command('/reschedule '+key+' 2026-12-01T01:00:00+00:00')
        self.assertIn('2026-12-01 09:00:00',self.fish.command('/reminders'))

    def test_reschedule_refuses_worker_claimed_finished_missing_and_non_reminders(self):
        key=self.fish.enqueue('reminder','事项',self.now+7200)
        other=self.fish.enqueue('research','研究')
        for state in ('running','succeeded','cancelled','failed'):
            with self.fish.db:self.fish.db.execute('UPDATE tasks SET state=? WHERE id=?',(state,key))
            self.assertIn('未修改',self.fish.command('/reschedule '+key+' 2026-12-01T09:00'))
            self.assertEqual(self.fish.db.execute('SELECT due FROM tasks WHERE id=?',(key,)).fetchone()[0],self.now+7200)
        for identifier in (other,'0'*12):
            self.assertIn('未修改',self.fish.command('/reschedule '+identifier+' 2026-12-01T09:00'))

    def test_invalid_time_or_identifier_does_not_change_due(self):
        key=self.fish.enqueue('reminder','事项',self.now+7200)
        for argument in (key+' yesterday',key+' 2020-01-01T09:00',key+' 2026-02-30T09:00','bad 2026-12-01T09:00'):
            with self.assertRaises(ValueError):self.fish.command('/reschedule '+argument)
        self.assertEqual(self.fish.db.execute('SELECT due FROM tasks').fetchone()[0],self.now+7200)

    def test_voice_read_allowed_writes_blocked_and_model_query_is_read_only(self):
        key=self.fish.enqueue('reminder','喝水',self.now+7200)
        self.assertIn('文字确认',self.fish.chat('修改提醒 '+key+' 到 2026-12-01T09:00',allow_actions=False))
        self.assertIn(key,self.fish.chat('我的提醒',allow_actions=False))
        self.model.plan.return_value={'action':'reminders','argument':'1','reply':'已经改时间了'}
        result=self.fish.chat('列一下接下来要提醒我的事')
        self.assertIn(key,result);self.assertNotIn('已经改',result)
        self.assertEqual(self.fish.db.execute('SELECT due FROM tasks').fetchone()[0],self.now+7200)

    def test_listing_handles_overdue_running_empty_and_pagination(self):
        self.assertIn('没有',self.fish.command('/reminders'))
        key=self.fish.enqueue('reminder','过期但尚未处理',self.now)
        self.assertIn('已到时间',self.fish.command('/reminders'))
        with self.fish.db:self.fish.db.execute("UPDATE tasks SET state='running' WHERE id=?",(key,))
        self.assertIn('正在处理',self.fish.command('/reminders'))
        for i in range(12):
            with self.fish.db:self.fish.db.execute("INSERT INTO tasks(id,kind,goal,state,due,created) VALUES (?,'reminder',?,'queued',?,?)",(str(i).zfill(12),'事项'+str(i),self.now+i+1,self.now))
        self.assertIn('2/2',self.fish.command('/reminders 2'))
        self.assertIn('这页没有',self.fish.command('/reminders 3'))
        with self.assertRaises(ValueError):self.fish.command('/reminders -1')

    def test_cancelled_turn_cannot_reschedule(self):
        key=self.fish.enqueue('reminder','喝水',self.now+7200);self.model.cancelled=lambda:True
        with self.assertRaises(ModelError):self.fish.chat('修改提醒 '+key+' 到 2026-12-01T09:00')
        self.assertEqual(self.fish.db.execute('SELECT due FROM tasks').fetchone()[0],self.now+7200)
