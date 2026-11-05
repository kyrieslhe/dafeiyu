import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock,patch
from dafeiyu.core import Fish,Model,ModelError


class UsageTests(unittest.TestCase):
    def test_record_only_actual_numeric_usage(self):
        model=Model();model.record_usage({'input_tokens':12,'cached_input_tokens':8,'output_tokens':3,'balance':999,'secret':'ignored','bad':True},.2,True)
        self.assertEqual(model.calls[0]['usage'],{'input_tokens':12,'cached_input_tokens':8,'output_tokens':3})
        model.record_usage(None,.1,False)
        self.assertEqual(model.calls[1]['usage'],{})
    def test_usage_persists_without_inventing_balance(self):
        with tempfile.TemporaryDirectory() as home:
            fish=Fish(home);fish.model.record_usage({'prompt_tokens':12,'completion_tokens':3},.2,True);fish.flush_usage('test-task')
            result=fish.command('/usage')
            self.assertEqual(result['recorded_attempts_24h'],1)
            self.assertEqual(result['reported_tokens'],{'input_tokens':12,'output_tokens':3})
            self.assertEqual(fish.model.calls,[]);fish.close()
    def test_cli_json_usage_contract(self):
        model=Model();model.codex='fake-codex'
        def process(command,**kwargs):
            Path(command[command.index('-o')+1]).write_text('hello')
            child=Mock();child.returncode=0;child.pid=999999
            child.communicate.return_value=(json.dumps({'type':'turn.completed','usage':{'input_tokens':7,'output_tokens':2}})+'\n','')
            return child
        with patch('dafeiyu.core.subprocess.Popen',side_effect=process):
            self.assertEqual(model.codex_reply([{'role':'user','content':'hello'}]),'hello')
        self.assertEqual(model.calls[0]['usage'],{'input_tokens':7,'output_tokens':2})
    def test_cancel_terminates_process_group_and_records_unknown_usage(self):
        model=Model();model.codex='fake-codex';model.cancelled=lambda:True
        child=Mock();child.pid=999999
        child.communicate.side_effect=[subprocess.TimeoutExpired('fake',.25),('','')]
        with patch('dafeiyu.core.subprocess.Popen',return_value=child),patch('dafeiyu.core.os.killpg') as kill:
            with self.assertRaises(ModelError):model.codex_reply([{'role':'user','content':'hello'}])
            kill.assert_called_once()
        self.assertEqual(model.calls[0]['usage'],{});self.assertFalse(model.calls[0]['success'])
    def test_history_is_bounded_without_truncating_current_user_input(self):
        with tempfile.TemporaryDirectory() as home:
            fish=Fish(home)
            with fish.db:
                fish.db.executemany('INSERT INTO messages(role,content,created) VALUES (?,?,?)',[('user' if n%2==0 else 'assistant','历史'*6000,fish.clock()) for n in range(16)])
            current='当前问题'*100
            context=fish.context(current)
            self.assertEqual(context[-1]['content'],current)
            self.assertLess(len(json.dumps(context,ensure_ascii=False).encode()),25000)
            fish.close()


if __name__=='__main__':unittest.main()
