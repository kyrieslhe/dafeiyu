import subprocess
import tempfile
import unittest
from dafeiyu.core import Fish
from dafeiyu.channel import tables
from dafeiyu.delivery import deliver
from dafeiyu.sharing import sent_context
from dafeiyu.conversation import initialize as conversations

class Followups(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.now=1793930400
        self.f=Fish(self.tmp.name,clock=lambda:self.now);tables(self.f)
        with self.f.db:self.f.db.execute("INSERT INTO channel_binding VALUES (1,'a','s',?)",(self.now,))
    def tearDown(self):self.f.close();self.tmp.cleanup()
    def notice(self,key,kind='explore',content='本鱼发现地月轨迹有一个回环。'):
        with self.f.db:
            self.f.db.execute("INSERT INTO tasks(id,kind,goal,state,result,created) VALUES (?,?,?,'succeeded',?,?)",(key,kind,'topic',content,self.now))
            self.f.db.execute('INSERT INTO outbox(task_id,content) VALUES (?,?)',(key,content))
    def accepted(self,command,**kwargs):return subprocess.CompletedProcess(command,0,'{}','')
    def test_only_channel_accepted_notices_enter_context(self):
        self.notice('first');self.assertEqual(sent_context(self.f),[])
        self.assertEqual(deliver(self.f,self.accepted),'accepted')
        self.assertEqual(sent_context(self.f)[0]['task_id'],'first')
        self.assertIn('回环',str(self.f.context('你刚发的那个是什么呀')))
        self.assertIn('不证明',sent_context(self.f)[0]['scope'])
    def test_unknown_and_legacy_deliveries_never_become_sent_memories(self):
        self.notice('first')
        with self.f.db:self.f.db.execute("INSERT INTO deliveries VALUES (1,'accepted',NULL,?)",(self.now,))
        self.assertEqual(sent_context(self.f),[])
        with self.f.db:self.f.db.execute('DELETE FROM deliveries')
        def timeout(*a,**k):raise subprocess.TimeoutExpired('send',60)
        self.assertEqual(deliver(self.f,timeout),'delivery_unknown');self.assertEqual(sent_context(self.f),[])
    def test_binding_change_and_clear_hide_old_delivery_context(self):
        self.notice('first');deliver(self.f,self.accepted)
        with self.f.db:self.f.db.execute("UPDATE channel_binding SET sender='new'")
        self.assertEqual(sent_context(self.f),[])
        with self.f.db:self.f.db.execute("UPDATE channel_binding SET sender='s'")
        self.assertTrue(sent_context(self.f));self.f.command('/clear');self.assertEqual(sent_context(self.f),[])
    def test_inflight_clear_does_not_restore_old_accepted_context(self):
        self.notice('first')
        def cleared(*a,**k):self.f.command('/clear');self.now+=2;return self.accepted(*a,**k)
        self.assertEqual(deliver(self.f,cleared),'accepted');self.assertEqual(sent_context(self.f),[])
    def test_due_reminder_bypasses_older_quiet_share(self):
        self.notice('first');self.notice('remind','reminder','喝水')
        self.f.command('/quiet 60');commands=[]
        def send(command,**kwargs):commands.append(command);return self.accepted(command,**kwargs)
        self.assertEqual(deliver(self.f,send),'accepted');self.assertIn('喝水',str(commands))
        self.assertEqual(self.f.db.execute('SELECT outbox_id FROM deliveries').fetchone()[0],2)
        self.assertEqual(sent_context(self.f),[])
    def test_due_reminder_is_not_blocked_by_pending_conversation(self):
        conversations(self.f);self.notice('remind','reminder','约好的提醒')
        with self.f.db:self.f.db.execute("INSERT INTO conversation_inbox(inbound_id,account,sender,content,state,created) VALUES ('i','a','s','还在聊','queued',?)",(self.now,))
        self.assertEqual(deliver(self.f,self.accepted),'accepted')
    def test_delivery_time_and_context_expiry_use_actual_finish(self):
        self.notice('first')
        def slow(*a,**k):self.now+=10;return self.accepted(*a,**k)
        deliver(self.f,slow);self.assertEqual(self.f.db.execute('SELECT updated FROM deliveries').fetchone()[0],self.now)
        self.now+=86401;self.assertEqual(sent_context(self.f),[])
