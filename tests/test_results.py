import tempfile
import unittest
from dafeiyu.core import Fish
from dafeiyu.results import pages


class ResultTests(unittest.TestCase):
    def test_pages_preserve_entire_unicode_report_and_sources(self):
        content=('🐳 海洋里的发现\n\n'+'鱼'*137+'\n')*110+'来源：https://example.org/ocean'
        chunks=pages(content)
        self.assertEqual(''.join(chunks),content)
        self.assertTrue(all(len(chunk)<=2400 for chunk in chunks))
        with tempfile.TemporaryDirectory() as home:
            fish=Fish(home)
            try:
                with fish.db:
                    fish.db.execute("INSERT INTO tasks(id,kind,goal,state,result,created) VALUES ('report','research','sea','succeeded',?,0)",(content,))
                first=fish.command('/result report')
                self.assertIn(chunks[0],first)
                self.assertIn('大肥鱼 /result report 2',first)
                last=fish.command('/result report '+str(len(chunks)))
                self.assertIn('来源：https://example.org/ocean',last)
                self.assertNotIn('下一页',last)
                for argument in ('report 0','report -1','report nope','report 1000000','report 1 extra','missing'):
                    self.assertIsInstance(fish.command('/result '+argument),str)
                self.assertEqual(fish.db.execute("SELECT result FROM tasks WHERE id='report'").fetchone()[0],content)
            finally:fish.close()
