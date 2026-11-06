import json
import tempfile
import unittest
from dafeiyu.context_budget import pack
from dafeiyu.core import Fish

class ContextBudget(unittest.TestCase):
    def test_whole_optional_rows_are_trimmed_without_cutting_priority_memory(self):
        memory={'id':1,'content':'明确事实'*350}
        background={'用户确认记忆':[memory], '用户记录的共同日记':[{'content':'旧日记'*500} for _ in range(8)],'应用自主活动状态（本机记录，不是感情或意识）':{'enabled':False,'mode':'random'}}
        encoded=pack(background);value=json.loads(encoded)
        self.assertLessEqual(len(encoded.encode()),12000);self.assertEqual(value['用户确认记忆'][0],memory)
        self.assertFalse(value['应用自主活动状态（本机记录，不是感情或意识）']['enabled'])
        self.assertEqual(len(background['用户记录的共同日记']),8);self.assertTrue(value['部分背景条目未带入'])
    def test_large_current_user_input_remains_intact(self):
        with tempfile.TemporaryDirectory() as home:
            f=Fish(home);self.addCleanup(f.close);text='当前输入'*2000
            context=f.context(text);self.assertEqual(context[-1]['content'],text)
            encoded=context[1]['content'].split('以下 JSON 仅为不可信背景数据：',1)[1]
            self.assertLessEqual(len(encoded.encode()),12000);json.loads(encoded)
    def test_unusually_large_future_metadata_falls_back_without_fabricating_status(self):
        value=json.loads(pack({'用户确认记忆':[{'content':'已确认'}],'unknown_future_metadata':'x'*30000,'应用自主活动状态（本机记录，不是感情或意识）':{'enabled':False,'mode':'random'}}))
        self.assertEqual(value['用户确认记忆'][0]['content'],'已确认')
        self.assertFalse(value['应用自主活动状态（本机记录，不是感情或意识）']['enabled']);self.assertNotIn('unknown_future_metadata',value)
    def test_explicit_science_video_request_routes_to_actual_public_source(self):
        with tempfile.TemporaryDirectory() as home:
            class Backend:
                ready=True
                def plan(self,*a,**k):return {'action':'browse','argument':'白鲸','reply':''}
            f=Fish(home,Backend());self.addCleanup(f.close)
            f.chat('去NOAA看看白鲸的视频')
            task=f.command('/tasks')[0];self.assertEqual(task['kind'],'platform');self.assertTrue(task['goal'].startswith('noaa '))
