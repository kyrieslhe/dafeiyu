from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from dafeiyu.core import Fish,ModelError
from dafeiyu.watching import sampled

class WatchPause(unittest.TestCase):
    def setUp(self):
        class Backend:
            ready=True
            cancelled=staticmethod(lambda:False)
        self.tmp=tempfile.TemporaryDirectory();self.f=Fish(self.tmp.name,Backend(),clock=lambda:1793930400);self.f.command('/watch on')
    def tearDown(self):self.f.close();self.tmp.cleanup()
    def test_disable_during_sampling_cancels_and_cleans_without_stale_choice(self):
        media=self.f.home/'test.mp4';media.write_bytes(b'fixture');original=self.f.model.cancelled
        def analyze(*a,**k):
            self.f.command('/watch off');self.assertTrue(self.f.model.cancelled())
            return 'old',{'recommend':True,'recommend_reason':'old'}
        with patch('dafeiyu.video.RUNTIME',self.f.home),patch('pathlib.Path.exists',return_value=True),patch('dafeiyu.public_video.download',return_value=(media,{'sha256':'fixture'})),patch('dafeiyu.video.analyze',side_effect=analyze):
            with self.assertRaisesRegex(ModelError,'关闭'):sampled(self.f,'https://example.org','ocean','curious-fixture',info={'title':'x','description':'x'})
        self.assertFalse(media.exists());self.assertIs(self.f.model.cancelled,original)
        self.assertEqual(self.f.db.execute('SELECT count(*) FROM video_choices').fetchone()[0],0)
    def test_off_suppresses_pending_automatic_clips_even_after_choice_overwrite(self):
        with self.f.db:
            self.f.db.execute('INSERT INTO video_runs VALUES (?)',('curious-old',))
            for key in ('curious-old','manual'):
                self.f.db.execute("INSERT INTO tasks(id,kind,goal,state,created) VALUES (?,'platform','video','succeeded',?)",(key,self.f.clock()))
                self.f.db.execute('INSERT INTO outbox(task_id,content) VALUES (?,?)',(key,'clip'))
            self.f.db.execute('INSERT INTO video_choices VALUES (?,?,?,?,?,?,?,?)',('https://example.org','manual','topic','title','sampled_clip',1,'reason',self.f.clock()))
        self.f.command('/watch off')
        suppressed=[row[0] for row in self.f.db.execute('SELECT outbox_id FROM curiosity_suppressed')]
        self.assertEqual(suppressed,[1])
    def test_off_after_report_write_still_prevents_notification_admission(self):
        self.f.command('/life random');key='curious-late'
        with self.f.db:self.f.db.execute("INSERT INTO tasks(id,kind,goal,state,due,created) VALUES (?,'explore','ocean','queued',?,?)",(key,self.f.clock(),self.f.clock()))
        original=Path.write_text
        def write(path,*a,**k):
            value=original(path,*a,**k)
            if path.name==key+'.md':self.f.command('/watch off')
            return value
        with patch('dafeiyu.platforms.choose',return_value=None),patch('dafeiyu.research.research',return_value=('observed',{'sources':[],'recommend':True,'scope':'sampled_clip_not_full_view'})),patch.object(Path,'write_text',write):self.f.tick()
        self.assertEqual(self.f.db.execute('SELECT state FROM tasks WHERE id=?',(key,)).fetchone()[0],'succeeded')
        self.assertEqual(self.f.db.execute('SELECT count(*) FROM outbox').fetchone()[0],0)
