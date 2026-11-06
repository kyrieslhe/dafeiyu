import tempfile
import unittest
import subprocess
from dafeiyu.core import Fish,ModelError
from dafeiyu.expressions import prepare,accepted,state


class Expressions(unittest.TestCase):
    def test_fixed_original_asset_and_only_accepted_sends_count(self):
        with tempfile.TemporaryDirectory() as home:
            f=Fish(home)
            path=prepare(f,'happy');self.assertEqual(path.suffix,'.png');self.assertTrue(path.read_bytes().startswith(b'\x89PNG'))
            self.assertEqual(state(f)['count'],0);accepted(f);self.assertIsNone(prepare(f,'curious'))
            f.command('/expressions off');self.assertIsNone(prepare(f,'sleepy'))
            for name in ('../../secret','/etc/passwd','https://example.org/image.png'):
                with self.assertRaises(ValueError):prepare(f,name)
            f.close()

    def test_buffered_expression_uses_only_staged_original_asset(self):
        from dafeiyu.channel import tables,inbound
        from dafeiyu.conversation import step
        class Planner:
            ready=True
            def plan(self,messages):return {'action':'express','argument':'happy','reply':'好耶，本鱼也替你开心！'}
        with tempfile.TemporaryDirectory() as home:
            now=[1793930400];f=Fish(home,Planner(),clock=lambda:now[0]);tables(f)
            with f.db:f.db.execute("INSERT INTO channel_binding VALUES (1,'a','s',0)")
            inbound(f,{'channel':'openclaw-weixin','group':False,'account':'a','sender':'s','message_id':'one','text':'今天有件开心的事','buffer_text':True});now[0]+=2
            commands=[]
            def send(command,**kwargs):commands.append(command);return subprocess.CompletedProcess(command,0,'{}','')
            self.assertEqual(step(f,send),'accepted')
            self.assertIn('--media',commands[0]);self.assertEqual(state(f)['count'],1)
            f.close()
