import json
import subprocess
import tempfile
import unittest
from dafeiyu.send_outcome import outcome
from dafeiyu.core import Fish
from dafeiyu.channel import tables,inbound
from dafeiyu.delivery import deliver
from dafeiyu.conversation import step
from dafeiyu.sharing import sent_context

def result(value,code=0):return subprocess.CompletedProcess('fixture',code,json.dumps(value),'')
class SendOutcome(unittest.TestCase):
    def test_exit_zero_cannot_override_explicit_structured_failure_or_dry_run(self):
        for value in [{'ok':False},{'payload':{'ok':False}},{'payload':{'result':{'success':False}}},{'dryRun':True},{'deliveryStatus':'suppressed'},{'deliveryStatus':'failed'},{'deliveryStatus':'queued'},[]]:
            self.assertNotEqual(outcome(result(value))[0],'accepted')
        self.assertEqual(outcome(result({'action':'send','dryRun':False,'payload':{'ok':True,'messageId':'fixture'}}))[0],'accepted')
        self.assertEqual(outcome(result({}))[0],'accepted')
    def test_partial_failure_never_schedules_context_retry(self):
        self.assertEqual(outcome(result({'ok':False,'error':'context_token expired','sentBeforeError':True}))[0],'delivery_unknown')
        self.assertEqual(outcome(result({'deliveryStatus':'partial_failed','error':'context expired'}))[0],'delivery_unknown')
        self.assertEqual(outcome(result({'deliveryStatus':'queued','error':'context expired'}))[0],'delivery_unknown')
    def test_context_and_auth_error_fields_classify_without_echoing_private_details(self):
        state,error=outcome(result({'ok':False,'error':{'message':'context_token expired PRIVATE_SENTINEL'}}))
        self.assertEqual(state,'waiting_context');self.assertNotIn('PRIVATE_SENTINEL',error)
        self.assertEqual(outcome(result({'payload':{'ok':False,'error':'403 forbidden PRIVATE_SENTINEL'}}))[0],'auth_failed')
        self.assertEqual(outcome(result({'ok':False,'payload':{'message':'context_token is a topic'}}))[0],'delivery_unknown')
    def test_proactive_denial_is_not_saved_as_accepted_share_and_is_not_blindly_replayed(self):
        with tempfile.TemporaryDirectory() as home:
            f=Fish(home,clock=lambda:1793930400);self.addCleanup(f.close);tables(f)
            with f.db:
                f.db.execute("INSERT INTO channel_binding VALUES (1,'a','s',?)",(f.clock(),))
                f.db.execute("INSERT INTO tasks(id,kind,goal,state,result,created) VALUES ('curious-fixture','explore','x','succeeded','x',?)",(f.clock(),))
                f.db.execute("INSERT INTO outbox(task_id,content) VALUES ('curious-fixture','a discovery')")
            calls=[]
            def denied(*a,**k):calls.append(1);return result({'ok':False,'deliveryStatus':'failed'})
            self.assertEqual(deliver(f,denied),'delivery_unknown');self.assertEqual(sent_context(f),[])
            self.assertIsNone(deliver(f,denied));self.assertEqual(len(calls),1)
    def test_chat_explicit_denial_does_not_persist_unsent_answer_as_spoken(self):
        with tempfile.TemporaryDirectory() as home:
            now=[1793930400]
            class Backend:
                ready=True
                def reply(self,*a):return 'should not be spoken'
            f=Fish(home,Backend(),lambda:now[0]);self.addCleanup(f.close);tables(f)
            with f.db:f.db.execute("INSERT INTO channel_binding VALUES (1,'a','s',?)",(now[0],))
            inbound(f,dict(channel='openclaw-weixin',account='a',sender='s',message_id='m',group=False,text='hello',buffer_text=True));now[0]+=2
            self.assertEqual(step(f,lambda *a,**k:result({'payload':{'ok':False}})),'delivery_unknown')
            reply=f.db.execute("SELECT content FROM messages WHERE role='assistant'").fetchone()[0]
            self.assertNotIn('should not be spoken',reply)
