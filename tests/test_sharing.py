import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from dafeiyu.core import Fish,ModelError
from dafeiyu.sharing import context,record,taste,parse
from dafeiyu.research import research

class Fake:
    ready=True
    def reply(self,messages):return 'fixture'

class Sharing(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.now=1793940000
        self.f=Fish(self.tmp.name,Fake(),lambda:self.now)
    def tearDown(self):self.f.close();self.tmp.cleanup()
    def quote(self,text,age=0):
        with self.f.db:self.f.db.execute("INSERT INTO messages(role,content,created) VALUES ('user',?,?)",(text,self.now-age))
    def automatic(self):
        self.f.command('/life random')
        identifier='curious-fixture'
        with self.f.db:
            self.f.db.execute("INSERT INTO tasks(id,kind,goal,state,due,created) VALUES (?,'explore','海洋鲸鱼','queued',?,?)",(identifier,self.now,self.now))
            self.f.db.execute('INSERT INTO interest_steps VALUES (?,?,NULL)',(identifier,'海洋鲸鱼'))
        return identifier
    def test_context_uses_only_relevant_recent_non_secret_dated_quotes(self):
        self.quote('我今天在想海洋鲸鱼是怎么睡觉的呀')
        self.quote('今天的蛋糕和草莓真好吃呀')
        self.quote('海洋鲸鱼项目密码是 secret-fixture')
        self.quote('我以前想研究海洋鲸鱼的声音',age=4*86400)
        value=context(self.f,'海洋鲸鱼')
        self.assertEqual(len(value['related_dated_quotes']),1)
        self.assertIn('怎么睡觉',value['related_dated_quotes'][0]['quote'])
        self.assertIn('2026',value['related_dated_quotes'][0]['at'])
    def test_private_quote_never_enters_public_search_input(self):
        class Backend:
            def search(self,messages):self.search_input=str(messages);return 'https://example.org/whale'
            def codex_reply(self,messages,**kwargs):
                self.synthesis=str(messages);return json.dumps({'report':'发现','recommend':False,'reason':'已知内容'})
        model=Backend();source={'url':'https://example.org/whale','text':'source','retrieved_at':'now','sha256':'fixture'}
        with patch('dafeiyu.research.fetch',return_value=source):
            _,meta=research(model,'鲸鱼',companion=True,discover=True,share_context={'quote':'PRIVATE_SENTINEL'})
        self.assertNotIn('PRIVATE_SENTINEL',model.search_input);self.assertIn('PRIVATE_SENTINEL',model.synthesis)
        self.assertIs(meta['recommend'],False)
    def test_taste_is_based_on_actual_choices_not_inferred_user_facts(self):
        row={'id':'a','goal':'海洋鲸鱼'}
        with self.f.db:record(self.f,row,{'recommend':True,'recommend_reason':'观察到了新信息'})
        value=taste(self.f);self.assertEqual(value['topics'][0]['recommended'],1)
        self.assertEqual(self.f.command('/memories'),[])
        self.now+=31*86400;self.assertEqual(taste(self.f)['recent'],[])
    def test_clear_removes_derived_quotes_choices_and_unsent_auto_notices(self):
        identifier=self.automatic();self.quote('我今天在想海洋鲸鱼怎么睡觉呢')
        with self.f.db:
            record(self.f,{'id':identifier,'goal':'海洋鲸鱼'},{'recommend':True,'recommend_reason':'interesting'})
            self.f.db.execute('INSERT INTO outbox(task_id,content) VALUES (?,?)',(identifier,'旧聊天衍生分享'))
        self.f.command('/clear')
        self.assertEqual(context(self.f,'海洋鲸鱼')['related_dated_quotes'],[])
        self.assertEqual(self.f.command('/taste')['recent'],[])
        self.assertTrue(self.f.db.execute('SELECT 1 FROM curiosity_suppressed').fetchone())
    def test_bad_judgment_fails_closed(self):
        for value in ('[]','null','{"report":"x","recommend":"false","reason":"x"}'):
            with self.assertRaises(ModelError):parse(value)
    def test_positive_choice_is_stored_and_queued_but_negative_is_quiet(self):
        identifier=self.automatic()
        with patch('dafeiyu.platforms.choose',return_value=None),patch('dafeiyu.research.research',return_value=('新发现',{'sources':[],'recommend':True,'recommend_reason':'新证据'})):
            self.f.tick()
        self.assertEqual(taste(self.f)['topics'][0]['recommended'],1)
        self.assertEqual(self.f.db.execute('SELECT count(*) FROM outbox WHERE task_id=?',(identifier,)).fetchone()[0],1)
    def test_reset_during_research_discards_old_background_without_notice(self):
        identifier=self.automatic()
        def researched(*args,**kwargs):
            self.f.command('/clear');return '不应恢复的旧聊天内容',{'sources':[],'recommend':True,'recommend_reason':'旧内容'}
        with patch('dafeiyu.platforms.choose',return_value=None),patch('dafeiyu.research.research',side_effect=researched):self.f.tick()
        self.assertEqual(self.f.db.execute('SELECT result FROM tasks WHERE id=?',(identifier,)).fetchone()[0],None)
        self.assertEqual(self.f.db.execute('SELECT count(*) FROM outbox').fetchone()[0],0)
        self.assertEqual(taste(self.f)['recent'],[])
    def test_background_errors_are_quiet_but_manual_errors_remain_visible(self):
        identifier=self.automatic()
        with patch('dafeiyu.platforms.choose',return_value=None),patch('dafeiyu.research.research',side_effect=ModelError('fixture failed')):self.f.tick()
        self.assertEqual(self.f.db.execute('SELECT state FROM tasks WHERE id=?',(identifier,)).fetchone()[0],'failed')
        self.assertEqual(self.f.db.execute('SELECT count(*) FROM outbox').fetchone()[0],0)
        self.f.enqueue('research','手动研究')
        with patch('dafeiyu.research.research',side_effect=ModelError('fixture failed')):self.f.tick()
        self.assertEqual(self.f.db.execute('SELECT count(*) FROM outbox').fetchone()[0],1)
    def test_preference_weights_remain_bounded_and_allow_uniform_exploration(self):
        from dafeiyu.sharing import choose_topic
        from unittest.mock import Mock
        with self.f.db:record(self.f,{'id':'a','goal':'海洋鲸鱼'},{'recommend':True,'recommend_reason':'new'})
        rng=Mock();rng.random.return_value=.5;rng.choice.side_effect=lambda items:items[0]
        choose_topic(self.f,['海洋鲸鱼','宇宙'],rng)
        options=rng.choice.call_args.args[0]
        self.assertEqual(options.count('海洋鲸鱼'),3);self.assertEqual(options.count('宇宙'),1)
        rng.random.return_value=.1;choose_topic(self.f,['海洋鲸鱼','宇宙'],rng)
        self.assertEqual(rng.choice.call_args.args[0],['海洋鲸鱼','宇宙'])
    def test_reset_after_report_write_before_commit_cannot_publish_stale_context(self):
        identifier=self.automatic();original=Path.write_text;cleared=[]
        def write(path,*args,**kwargs):
            result=original(path,*args,**kwargs)
            if path.name==identifier+'.md' and not cleared:
                cleared.append(True);self.f.command('/clear')
            return result
        with patch('dafeiyu.platforms.choose',return_value=None),patch('dafeiyu.research.research',return_value=('旧背景',{'sources':[],'recommend':True,'recommend_reason':'old'})),patch.object(Path,'write_text',write):self.f.tick()
        self.assertEqual(self.f.db.execute('SELECT result FROM tasks WHERE id=?',(identifier,)).fetchone()[0],None)
        self.assertEqual(self.f.db.execute('SELECT count(*) FROM outbox').fetchone()[0],0)
        self.assertEqual(taste(self.f)['recent'],[])
    def test_reset_during_video_judgment_cannot_restore_old_choice(self):
        from dafeiyu.watching import sampled
        media=self.f.home/'clip.mp4';media.write_bytes(b'fixture')
        def judged(*args,**kwargs):
            self.f.command('/clear');return 'old',{'recommend':True,'recommend_reason':'旧背景'}
        url='https://www.bilibili.com/video/BV1oBJo6GE22'
        info={'title':'fixture','description':'fixture'}
        with patch('dafeiyu.video.RUNTIME',self.f.home),patch('pathlib.Path.exists',return_value=True),patch('dafeiyu.public_video.resolve',return_value=info),patch('dafeiyu.public_video.download',return_value=(media,{'sha256':'fixture'})),patch('dafeiyu.video.analyze',side_effect=judged):
            with self.assertRaisesRegex(ModelError,'清空'):sampled(self.f,url,'海洋鲸鱼','curious-video')
        self.assertEqual(self.f.db.execute('SELECT count(*) FROM video_choices').fetchone()[0],0)
        self.assertFalse(media.exists())
    def test_followup_summaries_never_leak_back_into_later_searches(self):
        from dafeiyu.sharing import public_goal
        identifier=self.automatic()
        query=public_goal(self.f,identifier,'海洋鲸鱼，上一回用户说过 PRIVATE_SENTINEL')
        class Backend:
            def search(self,messages):self.public=str(messages);return 'https://example.org/source'
            def codex_reply(self,messages,**kwargs):return json.dumps({'report':'新内容','recommend':True,'reason':'new'})
        model=Backend();source={'url':'https://example.org/source','text':'public','sha256':'fixture','retrieved_at':'now'}
        with patch('dafeiyu.research.fetch',return_value=source):
            research(model,'旧原话 PRIVATE_SENTINEL',companion=True,discover=True,search_question=query)
        self.assertNotIn('PRIVATE_SENTINEL',model.public);self.assertIn('海洋鲸鱼',model.public)
    def test_clear_cancels_queued_auto_goal_containing_old_context(self):
        identifier=self.automatic();self.f.command('/clear')
        self.assertEqual(self.f.db.execute('SELECT state FROM tasks WHERE id=?',(identifier,)).fetchone()[0],'cancelled')
