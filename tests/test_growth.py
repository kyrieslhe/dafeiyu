import json
import tempfile
import unittest
from dafeiyu.core import Fish
from dafeiyu.growth import propose,apply,enabled

class Growth(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.now=1793930400;parent=self
        class Backend:
            ready=True
            cancelled=staticmethod(lambda:False)
            def codex_reply(self,messages,**kwargs):parent.calls.append(messages);return json.dumps({'topic':'鲸类声学','reason':'公开来源介绍了回声定位，值得继续了解。'})
        self.calls=[];self.f=Fish(self.tmp.name,Backend(),lambda:self.now);self.f.command('/interest 海洋');self.f.command('/growth on')
        with self.f.db:
            self.f.db.execute('INSERT INTO interest_steps VALUES (?,?,NULL)',('curious-fixture','海洋'))
            for n in range(2):self.f.db.execute('INSERT INTO discovery_choices VALUES (?,?,?,?,?,?)',(str(n),'海洋',1,'actual','source_text',self.now))
        self.row={'id':'curious-fixture','goal':'PRIVATE_SENTINEL','result':'PRIVATE_SENTINEL'}
        self.meta={'recommend':True,'recommend_reason':'PRIVATE_SENTINEL','sources':[{'url':'https://example.org/whale','text':'Public whale echolocation text','title':'Whale sounds'}]}
    def tearDown(self):self.f.close();self.tmp.cleanup()
    def test_public_only_proposal_adds_one_interest_with_source_provenance(self):
        value=propose(self.f,self.row,self.meta)
        self.assertNotIn('PRIVATE_SENTINEL',str(self.calls));self.assertIn('Public whale',str(self.calls))
        with self.f.db:apply(self.f,self.row,value)
        self.assertTrue(self.f.db.execute("SELECT 1 FROM interests WHERE topic='鲸类声学'").fetchone())
        self.assertEqual(self.f.command('/memories'),[]);self.assertEqual(json.loads(self.f.command('/growth')['added'][0]['sources']),['https://example.org/whale'])
    def test_disabled_or_insufficient_history_never_calls_model(self):
        self.f.command('/growth off');self.assertIsNone(propose(self.f,self.row,self.meta));self.assertEqual(self.calls,[])
        self.f.command('/growth on')
        with self.f.db:self.f.db.execute('DELETE FROM discovery_choices')
        self.assertIsNone(propose(self.f,self.row,self.meta));self.assertEqual(self.calls,[])
    def test_attempt_cadence_is_seven_days_even_when_model_declines(self):
        self.f.model.codex_reply=lambda *a,**k:'{"topic":"","reason":"没有新方向"}'
        self.assertIsNone(propose(self.f,self.row,self.meta));self.assertIsNone(propose(self.f,self.row,self.meta))
        last=self.f.command('/growth')['last_attempt'];self.assertEqual(last,self.now)
        self.now+=7*86400+1;self.assertIsNone(propose(self.f,self.row,self.meta));self.assertGreater(self.f.command('/growth')['last_attempt'],last)
    def test_owner_removed_topic_is_not_restored_but_explicit_readd_is_allowed(self):
        self.f.command('/interest 鲸类声学');identifier=self.f.db.execute("SELECT id FROM interests WHERE topic='鲸类声学'").fetchone()[0]
        self.f.command('/uninterest '+str(identifier));value=propose(self.f,self.row,self.meta)
        with self.f.db:apply(self.f,self.row,value)
        self.assertFalse(self.f.db.execute("SELECT 1 FROM interests WHERE topic='鲸类声学'").fetchone())
        self.f.command('/interest 鲸类声学');self.assertTrue(self.f.db.execute("SELECT 1 FROM interests WHERE topic='鲸类声学'").fetchone())
    def test_removed_parent_or_disabled_setting_cannot_apply_inflight_proposal(self):
        value=propose(self.f,self.row,self.meta);self.f.command('/uninterest 1')
        with self.f.db:apply(self.f,self.row,value)
        self.assertEqual(len(self.f.command('/interest')),0)
        self.f.command('/interest 海洋');self.f.command('/growth off')
        with self.f.db:apply(self.f,self.row,value)
        self.assertFalse(self.f.db.execute("SELECT 1 FROM interests WHERE topic='鲸类声学'").fetchone())
    def test_eight_interest_cap_leaves_room_for_manual_choices(self):
        for n in range(7):self.f.command('/interest topic'+str(n))
        self.assertIsNone(propose(self.f,self.row,self.meta));self.assertEqual(self.calls,[])
        self.f.command('/interest manual');self.assertEqual(len(self.f.command('/interest')),9)
    def test_clear_during_proposal_cannot_add_an_old_context_topic(self):
        def cleared(*a,**k):self.f.command('/clear');return '{"topic":"鲸类声学","reason":"public"}'
        self.f.model.codex_reply=cleared;value=propose(self.f,self.row,self.meta)
        with self.f.db:apply(self.f,self.row,value)
        self.assertFalse(self.f.db.execute("SELECT 1 FROM interests WHERE topic='鲸类声学'").fetchone())
    def test_cancellation_prevents_optional_extra_call(self):
        self.f.model.cancelled=lambda:True
        self.assertIsNone(propose(self.f,self.row,self.meta));self.assertEqual(self.calls,[])
    def test_disable_control_cancels_only_optional_planning_immediately(self):
        from dafeiyu.channel import tables,inbound
        tables(self.f)
        with self.f.db:self.f.db.execute("INSERT INTO channel_binding VALUES (1,'a','s',0)")
        def stop(*a,**k):
            inbound(self.f,dict(channel='openclaw-weixin',account='a',sender='s',message_id='off',group=False,text='/growth off',buffer_text=True))
            self.assertTrue(self.f.model.cancelled());return '{"topic":"鲸类声学","reason":"public"}'
        self.f.model.codex_reply=stop;value=propose(self.f,self.row,self.meta)
        with self.f.db:apply(self.f,self.row,value)
        self.assertFalse(enabled(self.f));self.assertEqual(len(self.f.command('/interest')),1)
    def test_other_provider_never_implicitly_switches_to_codex(self):
        self.f.model.provider='api';self.assertIsNone(propose(self.f,self.row,self.meta));self.assertEqual(self.calls,[])
