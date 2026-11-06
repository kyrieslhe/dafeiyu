import tempfile
import unittest
from dafeiyu.core import Fish,ModelError
from dafeiyu.channel import tables,inbound
from dafeiyu.conversation import step
from dafeiyu.relationship import context


class Reset(unittest.TestCase):
    def event(self,message,text,sender='s'):
        return {'channel':'openclaw-weixin','group':False,'account':'a','sender':sender,'message_id':message,'text':text,'buffer_text':True}
    def test_clear_and_forget_do_not_automatically_reinject_old_task_results(self):
        with tempfile.TemporaryDirectory() as home:
            f=Fish(home,clock=lambda:1000)
            with f.db:f.db.execute("INSERT INTO tasks(id,kind,goal,state,result,created) VALUES ('old','research','private question','succeeded','old answer',999)")
            self.assertTrue(context(f,'刚才的任务')['最近任务实际状态（成功不等于送达）'])
            memory=f.remember('这是需要删除的明确原话')
            f.command('/forget '+memory.split('（')[1].split('）')[0])
            self.assertEqual(context(f,'刚才的任务')['最近任务实际状态（成功不等于送达）'],[])
            self.assertIn('old answer',f.command('/result old'));f.close()
    def test_priority_pause_cancels_old_generation_without_waiting_for_its_reply(self):
        with tempfile.TemporaryDirectory() as home:
            now=[1793930400];f=Fish(home,clock=lambda:now[0]);tables(f)
            with f.db:f.db.execute("INSERT INTO channel_binding VALUES (1,'a','s',0)")
            receive=lambda message,text:inbound(f,self.event(message,text))
            class Model:
                ready=True
                cancelled=staticmethod(lambda:False)
                def reply(self,messages):
                    result=receive('two','/pause')
                    assert '暂停' in result
                    assert self.cancelled()
                    raise ModelError('cancelled')
            f.model=Model();receive('one','说个长一点的故事');now[0]+=2
            self.assertEqual(step(f,lambda *a,**k:self.fail('sent superseded reply')),'superseded')
            self.assertFalse(f.model.cancelled())
            user=f.db.execute("SELECT content FROM messages WHERE role='user'").fetchone()[0]
            self.assertEqual(user,'说个长一点的故事');f.close()
    def test_old_binding_queue_does_not_block_new_approved_identity(self):
        with tempfile.TemporaryDirectory() as home:
            now=[1793930400];f=Fish(home,clock=lambda:now[0]);tables(f)
            with f.db:f.db.execute("INSERT INTO channel_binding VALUES (1,'a','s',0)")
            for n in range(12):inbound(f,self.event(str(n),'旧身份待处理文字'))
            with f.db:f.db.execute("UPDATE channel_binding SET sender='new'")
            inbound(f,self.event('new','/tasks',sender='new'));now[0]+=2
            import subprocess
            result=step(f,lambda *a,**k:subprocess.CompletedProcess('send',0,'{}',''))
            self.assertEqual(result,'accepted')
            self.assertEqual(f.db.execute("SELECT count(*) FROM conversation_inbox WHERE state='identity_changed'").fetchone()[0],12);f.close()

    def test_explicit_single_message_or_formal_request_preserves_whole_reply(self):
        from dafeiyu.conversation import bubbles
        text='一个观点。\n\n第二个观点。'
        self.assertEqual(bubbles(text,'请一次发完'),[text])
        self.assertEqual(bubbles(text,'正式说明'),[text])
        self.assertEqual(len(bubbles(text,'今天有个好消息')),2)

    def test_reset_during_planning_cannot_write_a_stale_memory(self):
        with tempfile.TemporaryDirectory() as home:
            f=Fish(home)
            class Planner:
                ready=True
                def plan(self,messages):
                    f.command('/clear')
                    return {'action':'remember','argument':'我喜欢海洋','reply':''}
            f.model=Planner()
            with self.assertRaisesRegex(ModelError,'重置'):f.chat('请记住我喜欢海洋')
            self.assertEqual(f.command('/memories'),[]);f.close()
    def test_reset_during_plain_reply_cannot_restore_cleared_messages(self):
        with tempfile.TemporaryDirectory() as home:
            f=Fish(home)
            class Reply:
                ready=True
                def reply(self,messages):f.command('/clear');return '不应写回的旧稿'
            f.model=Reply()
            with self.assertRaisesRegex(ModelError,'重置'):f.chat('原来的问题')
            self.assertEqual(f.db.execute('SELECT count(*) FROM messages').fetchone()[0],0);f.close()
