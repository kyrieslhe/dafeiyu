import tempfile
import unittest
from dafeiyu.core import Fish
from dafeiyu.platforms import choose

class WorkingSources(unittest.TestCase):
    def test_automatic_routes_never_select_restricted_platforms(self):
        with tempfile.TemporaryDirectory() as home:
            f=Fish(home);self.addCleanup(f.close);f.command('/watch on')
            for topic in ('海洋与动物','宇宙与自然科学','AI 与开源工具','日常生活的有趣知识'):
                selected=set()
                for n in range(30):
                    key='curious-'+str(n)
                    with f.db:f.db.execute('INSERT OR REPLACE INTO interest_steps VALUES (?,?,NULL)',(key,topic))
                    selected.add(choose(f,key))
                self.assertFalse(selected&{'bilibili','douyin'})
                self.assertEqual(selected,{None,'noaa'} if '海洋' in topic else ({None,'nasa'} if '宇宙' in topic else {None}))
    def test_disabled_or_cooled_sources_fall_back_to_regular_research(self):
        with tempfile.TemporaryDirectory() as home:
            f=Fish(home);self.addCleanup(f.close);f.command('/watch on')
            key=next('curious-'+str(n) for n in range(30) if sum(('curious-'+str(n)).encode())%2==0)
            with f.db:f.db.execute('INSERT INTO interest_steps VALUES (?,?,NULL)',(key,'海洋与动物'))
            self.assertEqual(choose(f,key),'noaa')
            f.command('/watch off');self.assertIsNone(choose(f,key));f.command('/watch on')
            f.command('/platforms off');self.assertIsNone(choose(f,key));f.command('/platforms on')
            with f.db:f.db.execute('INSERT INTO platform_visits VALUES(NULL,?,?,?,?)',('noaa','','sample_unavailable',f.clock()))
            self.assertIsNone(choose(f,key))
