import json
import tempfile
import unittest
from unittest.mock import patch
from dafeiyu.core import Fish,ModelError
from dafeiyu.research import research,ResearchError,Text
from dafeiyu.feeds import entries

RSS='<rss><channel><item><title>A</title><link>https://example.org/a</link><pubDate>2026-01-01</pubDate></item><item><title>B</title><link>https://example.org/b</link></item></channel></rss>'
def source(url,text):return {'url':url,'text':text,'retrieved_at':'now','sha256':'fixture'}
class Backend:
    def __init__(self):self.searches=0;self.syntheses=0
    def search(self,messages):self.searches+=1;return 'https://example.org/search'
    def codex_reply(self,*a,**k):
        self.syntheses+=1
        return json.dumps({'report':'具体发现','recommend':True,'reason':'new'})

class FeedFirst(unittest.TestCase):
    def test_fresh_article_uses_one_synthesis_without_search(self):
        model=Backend()
        with patch('dafeiyu.research.fetch',side_effect=lambda url:source(url,RSS if url.endswith('/feed') else 'Full article')):
            _,meta=research(model,'海洋',companion=True,discover=True,feed_urls=['https://example.org/feed'])
        self.assertEqual(model.searches,0);self.assertTrue(meta['feed_first']);self.assertEqual(meta['fetch_attempts'],2)
        self.assertEqual(meta['sources'][1]['published_at'],'2026-01-01')
    def test_failed_first_article_tries_next_unread_within_budget(self):
        model=Backend()
        def fetch(url):
            if url.endswith('/a'):raise ResearchError('fixture unavailable')
            return source(url,RSS if url.endswith('/feed') else 'full body')
        with patch('dafeiyu.research.fetch',side_effect=fetch):
            _,meta=research(model,'海洋',companion=True,discover=True,feed_urls=['https://example.org/feed'])
        self.assertEqual(meta['feed_entries'],['https://example.org/b']);self.assertEqual(meta['fetch_attempts'],3);self.assertEqual(model.searches,0)
    def test_all_seen_returns_to_search_and_directory_alone_never_recommends(self):
        model=Backend()
        def fetch(url):
            if not url.endswith('/feed'):raise ResearchError('unavailable')
            return source(url,RSS)
        with patch('dafeiyu.research.fetch',side_effect=fetch):
            _,meta=research(model,'海洋',companion=True,discover=True,feed_urls=['https://example.org/feed'],seen_urls={'https://example.org/a','https://example.org/b'})
        self.assertEqual(model.searches,1);self.assertIs(meta['recommend'],False);self.assertEqual(model.syntheses,0);self.assertEqual(meta['scope'],'feed_directory_only')
    def test_failed_attempts_count_toward_four_fetch_limit(self):
        model=Backend();model.search=lambda *a:' '.join('https://example.org/'+str(n) for n in range(10))
        calls=[]
        def fetch(url):calls.append(url);raise ResearchError('fixture')
        with patch('dafeiyu.research.fetch',side_effect=fetch):
            with self.assertRaises(ResearchError) as error:research(model,'海洋',feed_urls=['https://example.org/feed'])
        self.assertEqual(len(calls),4);self.assertEqual(len(error.exception.failures),4)
    def test_cancellation_prevents_feed_retrieval_and_search(self):
        model=Backend();model.cancelled=lambda:True
        with patch('dafeiyu.research.fetch') as get:
            with self.assertRaises(ResearchError):research(model,'海洋',feed_urls=['https://example.org/feed'])
            get.assert_not_called();self.assertEqual(model.searches,0)
    def test_links_are_opt_in_bounded_and_feed_dates_preserved(self):
        parser=Text();parser.feed('<a href="/clip.mp4">x</a>');self.assertEqual(parser.links,[])
        parser=Text(True);parser.feed('<a href="/clip.mp4">x</a>'*250);self.assertEqual(len(parser.links),200)
        self.assertEqual(entries(RSS)[0]['published_at'],'2026-01-01')
    def test_failed_source_evidence_is_saved_in_private_storage(self):
        with tempfile.TemporaryDirectory() as home:
            f=Fish(home,Backend());self.addCleanup(f.close);key=f.enqueue('research','question')
            error=ResearchError('failed');error.failures=[{'url':'https://example.org','error':'not available'}]
            with patch('dafeiyu.research.research',side_effect=error):f.tick()
            evidence=f.home/'reports'/(key+'.failure.json');self.assertTrue(evidence.exists());self.assertEqual(evidence.stat().st_mode&0o777,0o600)
    def test_automatic_source_sampling_stops_before_lease_expires(self):
        from dafeiyu.core import Model
        with tempfile.TemporaryDirectory() as home:
            f=Fish(home,Model(),clock=lambda:1793930400);self.addCleanup(f.close);f.command('/life random');key='curious-deadline'
            with f.db:f.db.execute("INSERT INTO tasks(id,kind,goal,state,due,created) VALUES (?,'explore','ocean','queued',?,?)",(key,f.clock(),f.clock()))
            elapsed=[0]
            def researched(*a,**k):
                elapsed[0]=541;self.assertTrue(f.model.cancelled());return 'too late',{'sources':[],'recommend':True}
            with patch('dafeiyu.core.time.monotonic',side_effect=lambda:elapsed[0]),patch('dafeiyu.quota.guard',return_value={'status':'ok'}),patch('dafeiyu.platforms.choose',return_value=None),patch('dafeiyu.research.research',side_effect=researched):f.tick()
            self.assertEqual(f.db.execute('SELECT state FROM tasks WHERE id=?',(key,)).fetchone()[0],'failed')
            self.assertEqual(f.db.execute('SELECT count(*) FROM outbox').fetchone()[0],0)
