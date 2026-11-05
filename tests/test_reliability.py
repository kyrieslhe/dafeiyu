import subprocess
import tempfile
import unittest
from dafeiyu.core import Fish,ModelError
from dafeiyu.channel import inbound,tables,health
from dafeiyu.delivery import deliver


class Failed:
    ready=True
    def reply(self,messages):raise ModelError('测试模型不可用')


class ReliabilityTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.now=1793854800.0
        self.fish=Fish(self.tmp.name,Failed(),lambda:self.now);tables(self.fish)
        with self.fish.db:self.fish.db.execute('INSERT INTO channel_binding VALUES (1,?,?,?)',('a','s',self.now))
    def tearDown(self):self.fish.close();self.tmp.cleanup()
    def event(self):return dict(channel='openclaw-weixin',account='a',sender='s',message_id='m',group=False,text='/tasks')
    def test_failed_task_has_one_durable_failure_notice_and_no_fake_report(self):
        key=self.fish.enqueue('draft','test');self.fish.tick();self.fish.tick()
        rows=self.fish.command('/inbox');self.assertEqual(len(rows),1);self.assertIn('没有完成',rows[0]['content'])
        self.assertFalse((self.fish.home/'reports'/(key+'.md')).exists())
        calls=[]
        def send(command,**kwargs):calls.append(command);return subprocess.CompletedProcess(command,0,'{}','')
        self.assertEqual(deliver(self.fish,send),'accepted');self.assertIsNone(deliver(self.fish,send));self.assertEqual(len(calls),1)
    def test_expired_task_not_replayed_and_notice_is_deduplicated(self):
        key=self.fish.enqueue('draft','test')
        with self.fish.db:self.fish.db.execute("UPDATE tasks SET state='running',lease=? WHERE id=?",(self.now-1,key))
        self.fish.tick();self.fish.tick()
        self.assertEqual(len(self.fish.command('/inbox')),1)
        self.assertEqual(self.fish.command('/tasks')[0]['state'],'failed')
    def test_duplicate_does_not_extend_delivery_window_or_count_twice(self):
        event=self.event();inbound(self.fish,event);seen=self.now;self.now+=200;inbound(self.fish,event)
        self.assertEqual(self.fish.db.execute('SELECT last_seen FROM channel_binding').fetchone()[0],seen)
        self.assertEqual(health(self.fish)['inbound_24h'],1)
        self.assertEqual(health(self.fish)['seconds_since_inbound'],200)
    def test_failed_chat_is_counted_separately_from_delivery(self):
        event=self.event();event['text']='你好';self.assertIn('不可用',inbound(self.fish,event))
        value=self.fish.command('/health');self.assertEqual(value['outcomes']['failed'],1)
        self.assertEqual(value['delivery_states'],[])
        self.assertNotIn('account',value);self.assertEqual(value['p95_processing_seconds'],0)
