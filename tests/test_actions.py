import tempfile
import unittest
from dafeiyu.core import Fish,ModelError


class Planner:
    ready=True
    def __init__(self,proposal):self.proposal=proposal;self.calls=0
    def plan(self,messages):self.calls+=1;return self.proposal


class ActionTests(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.fish=Fish(self.tmp.name)
    def tearDown(self):self.fish.close();self.tmp.cleanup()
    def plan(self,action,argument='',reply=''):
        self.fish.model=Planner(dict(action=action,argument=argument,reply=reply))
    def test_ordinary_chat_is_one_call_without_tasks(self):
        self.plan('reply',reply='跑步顺利，回来再聊。')
        self.assertEqual(self.fish.chat('我去跑步了'),'跑步顺利，回来再聊。')
        self.assertEqual(self.fish.model.calls,1)
        self.assertEqual(self.fish.command('/tasks'),[])
    def test_natural_research_creates_real_task_not_fake_completion(self):
        self.plan('research','Python 官方版本',reply='我已经查好了')
        result=self.fish.chat('能去核对一下 Python 当前的版本吗？')
        self.assertIn('研究任务已入队',result);self.assertNotIn('已经查好',result)
        self.assertEqual(self.fish.command('/tasks')[0]['state'],'queued')
    def test_model_cannot_apply_or_enable_autonomy(self):
        for action in ['approve','life','shell','delete','send_message']:
            self.plan(action)
            with self.assertRaises(ModelError):self.fish.chat('看看这段资料')
        self.assertEqual(self.fish.command('/life')['plan'][0]['enabled'],0)
    def test_inferred_memory_rejected(self):
        self.plan('remember','我喜欢爵士乐')
        self.fish.chat('你猜我的爱好？')
        self.assertEqual(self.fish.command('/memories'),[])
    def test_explicit_memory_must_be_current_literal_quote(self):
        self.plan('remember','我喜欢爵士乐')
        self.fish.chat('你可以帮我记住我喜欢爵士乐吗？')
        self.assertEqual(self.fish.command('/memories')[0]['content'],'我喜欢爵士乐')
        self.plan('remember','我喜欢古典音乐')
        self.fish.chat('你可以记住我的爱好吗？')
        self.assertEqual(len(self.fish.command('/memories')),1)
    def test_negative_request_never_writes_memory(self):
        self.plan('remember','我喜欢爵士乐')
        self.fish.chat('不要记住我喜欢爵士乐')
        self.assertEqual(self.fish.command('/memories'),[])
    def test_invalid_schema_never_executes(self):
        self.fish.model=Planner({'action':'research','argument':'x','reply':'','extra':True})
        with self.assertRaises(ModelError):self.fish.chat('你好')
        self.assertEqual(self.fish.command('/tasks'),[])
    def test_model_diary_not_literal_is_rejected(self):
        self.plan('diary','今天我们一起去看了海')
        self.fish.chat('写一段日记吧')
        self.assertEqual(self.fish.command('/diary'),[])
    def test_model_cannot_implicitly_schedule_a_reminder(self):
        self.plan('reminder','2027-01-01T09:00:00+08:00 起床')
        self.fish.chat('早上好')
        self.assertEqual(self.fish.command('/tasks'),[])


if __name__=='__main__':unittest.main()
