import tempfile
import unittest
from unittest.mock import patch
from dafeiyu.core import Fish
from dafeiyu.feeds import entries,validate,for_topic
from dafeiyu.research import research

RSS='<rss><channel><item><title>New discovery</title><link>https://example.org/article</link><description>Real summary</description></item></channel></rss>'


class Feeds(unittest.TestCase):
    def test_bounded_feed_parser_and_untrusted_entity_rejection(self):
        self.assertEqual(entries(RSS)[0]['title'],'New discovery')
        self.assertEqual(len(entries(RSS.replace('Real summary','<![CDATA[example <!DOCTYPE html>]]>'))),1)
        atom='<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Paper</title><link href="https://example.org/paper"/></entry></feed>'
        self.assertEqual(entries(atom)[0]['url'],'https://example.org/paper')
        for text in ('<!DOCTYPE x [<!ENTITY x "bad">]><rss/>','x'*400001):
            with self.assertRaises(ValueError):entries(text)
        for url in ('http://example.org/feed','https://localhost/feed','https://127.0.0.1/rss','https://user:pass@example.org/rss'):
            with self.assertRaises(ValueError):validate(url)
    def test_public_feed_can_be_disabled_and_removed_without_becoming_user_fact(self):
        with tempfile.TemporaryDirectory() as home:
            f=Fish(home);self.assertTrue(f.command('/feeds')['enabled'])
            self.assertTrue(for_topic(f,'id','AI 开源'))
            f.command('/feeds off');self.assertEqual(for_topic(f,'id','AI'),[])
            self.assertEqual(f.command('/memories'),[]);f.close()
    def test_research_reads_new_entry_and_labels_directory_as_directory(self):
        class Model:
            def search(self,messages):return 'https://example.org/other'
            def reply(self,messages):
                self.messages=messages
                return '依据[文章](https://example.org/article)。'
        model=Model();calls=[]
        def fetch(url):
            calls.append(url)
            return {'url':url,'text':RSS if url.endswith('/feed') else 'article body','retrieved_at':'2026-11-06','sha256':'fixture','truncated':False}
        with patch('dafeiyu.research.fetch',side_effect=fetch):
            report,meta=research(model,'AI',feed_urls=['https://example.org/feed'])
        self.assertIn('https://example.org/article',meta['feed_entries'])
        self.assertIn('feed_index',str(model.messages));self.assertLessEqual(len(calls),4)
        with patch('dafeiyu.research.fetch',side_effect=fetch):
            report,meta=research(model,'AI',feed_urls=['https://example.org/feed'],seen_urls={'https://example.org/article'})
        self.assertEqual(meta['feed_entries'],[])
