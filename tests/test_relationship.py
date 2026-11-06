import tempfile
import unittest
from dafeiyu.core import Fish
from dafeiyu.relationship import context,task_reply


class Relationship(unittest.TestCase):
    def test_dated_original_quotes_are_not_inferred_facts_and_clear_removes_them(self):
        with tempfile.TemporaryDirectory() as home:
            f=Fish(home,clock=lambda:1793930400)
            with f.db:
                for offset,text in ((2,'前天我正在为一个报告准备材料。'),(1,'昨天我去海边看了一会儿日落。'),(0,'今天有一个挺有意思的想法。')):
                    f.db.execute("INSERT INTO messages(role,content,created) VALUES ('user',?,?)",(text,f.clock()-offset*86400))
            data=context(f);self.assertEqual(len(data['过去真实原话（可过时，不推断性格）']),3)
            self.assertEqual(f.command('/memories'),[])
            f.command('/clear');self.assertEqual(context(f)['过去真实原话（可过时，不推断性格）'],[]);f.close()
    def test_followup_uses_real_task_state_instead_of_asking_for_ticket(self):
        with tempfile.TemporaryDirectory() as home:
            f=Fish(home)
            with f.db:f.db.execute("INSERT INTO tasks(id,kind,goal,state,result,created) VALUES ('a','research','海洋声音','succeeded','真实来源支持的发现。',?)",(f.clock(),))
            answer=task_reply(f);self.assertIn('已经做完',answer);self.assertIn('真实来源',answer);self.assertNotIn('已经送达',answer)
            f.close()
