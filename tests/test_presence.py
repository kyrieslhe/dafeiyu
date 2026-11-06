import tempfile
import unittest
from dafeiyu.core import Fish
from dafeiyu.presence import observe,status
from dafeiyu.channel import tables
from dafeiyu.delivery import deliver


class Presence(unittest.TestCase):
    def test_explicit_rest_busy_and_return_are_temporary_not_personal_facts(self):
        with tempfile.TemporaryDirectory() as home:
            f=Fish(home,clock=lambda:1793930400)
            for text in ('我去睡觉了','晚安'):
                with f.db:observe(f,text)
                self.assertEqual(status(f)['mode'],'resting')
            with f.db:observe(f,'我回来啦，继续聊')
            self.assertEqual(status(f)['mode'],'available')
            with f.db:observe(f,'我先去开会')
            self.assertEqual(status(f)['mode'],'busy')
            for text in ('我还没睡觉','我去睡觉？','你怎么总是说晚安'):
                with f.db:observe(f,text)
                self.assertEqual(status(f)['mode'],'available')
            self.assertEqual(f.command('/memories'),[]);f.close()
    def test_quiet_defers_proactive_send_without_claiming_delivered(self):
        with tempfile.TemporaryDirectory() as home:
            f=Fish(home,clock=lambda:1793930400);tables(f)
            with f.db:
                f.db.execute("INSERT INTO channel_binding VALUES(1,'a','s',0)")
                f.db.execute("INSERT INTO tasks(id,kind,goal,state,created) VALUES('a','explore','x','succeeded',0)")
                f.db.execute("INSERT INTO outbox(task_id,content) VALUES('a','真实发现')")
            f.command('/quiet 60')
            self.assertIsNone(deliver(f,lambda *a,**k:self.fail('interrupted user')))
            self.assertEqual(f.db.execute('SELECT count(*) FROM deliveries').fetchone()[0],0)
            f.command('/quiet off');self.assertEqual(status(f)['mode'],'available')
            f.close()
