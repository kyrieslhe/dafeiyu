import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import Mock,patch
import zlib
from dafeiyu.channel import inbound,tables
from dafeiyu.core import Fish,Model,ModelError
from dafeiyu.media import staged_images,MediaError


def png(width=16,height=16):
    def chunk(name,data):return struct.pack('>I',len(data))+name+data+struct.pack('>I',zlib.crc32(name+data)&0xffffffff)
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,2,0,0,0))+chunk(b'IDAT',zlib.compress((b'\0'+b'\x00\x66\xff'*width)*height))+chunk(b'IEND',b'')


class Vision:
    ready=True
    def __init__(self):self.paths=[]
    def plan(self,messages,images=None):
        self.paths=images or []
        assert all(Path(p).exists() for p in self.paths)
        return {'action':'reply','argument':'','reply':'看到了蓝色图片。'}


class MediaTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.home=Path(self.tmp.name).resolve()
        self.image=self.home/'gateway/media/inbound/photo.png';self.image.parent.mkdir(parents=True);self.image.write_bytes(png())
    def tearDown(self):self.tmp.cleanup()
    def event(self):return dict(channel='openclaw-weixin',account='a',sender='s',message_id='m',group=False,text='',media=[{'path':str(self.image)}])
    def fish(self):
        f=Fish(self.home,Vision());tables(f)
        with f.db:f.db.execute('INSERT INTO channel_binding VALUES (1,?,?,?)',('a','s',0))
        self.addCleanup(f.close);return f
    def test_authorized_image_uses_staged_copy_then_removes_it(self):
        f=self.fish();self.assertIn('蓝色',inbound(f,self.event()))
        self.assertTrue(f.model.paths);self.assertTrue(all(not Path(p).exists() for p in f.model.paths))
        self.assertNotIn(str(self.image),json.dumps(f.rows('SELECT * FROM messages')))
        self.assertTrue(self.image.exists())
    def test_identity_gate_runs_before_file_read(self):
        f=Fish(self.home,Vision());tables(f);self.addCleanup(f.close)
        with patch('dafeiyu.media.staged_images',side_effect=AssertionError('opened before identity')):
            self.assertIn('绑定',inbound(f,self.event()))
    def test_outside_paths_symlinks_and_url_refused(self):
        outside=self.home/'secret.png';outside.write_bytes(png())
        linked=self.image.parent/'link.png';linked.symlink_to(outside)
        for name in [str(outside),str(linked),'https://example.com/image.png',str(self.image.parent/'../inbound/photo.png')]:
            with self.assertRaises(MediaError):
                with staged_images(self.home,[{'path':name}]):self.fail('admitted unsafe path')
    def test_non_image_and_large_resolution_refused(self):
        for data in [b'not an image',png(1,1)[:16]+struct.pack('>II',30000,30000)+b'\0'*10]:
            self.image.write_bytes(data)
            with self.assertRaises(MediaError):
                with staged_images(self.home,[{'path':str(self.image)}]):self.fail('invalid media')
    def test_cleanup_even_when_model_fails(self):
        with self.assertRaisesRegex(RuntimeError,'failure'):
            with staged_images(self.home,[{'path':str(self.image)}]) as paths:
                target=Path(paths[0]);raise RuntimeError('failure')
        self.assertFalse(target.exists())
    def test_codex_attaches_image_without_shell_or_file_tool(self):
        model=Model();model.codex='fake-codex';commands=[]
        def start(command,**kwargs):
            commands.append(command);Path(command[command.index('-o')+1]).write_text('vision reply')
            p=Mock();p.returncode=0;p.communicate.return_value=('','');return p
        with patch('dafeiyu.core.subprocess.Popen',side_effect=start):
            self.assertEqual(model.codex_reply([{'role':'user','content':'看看图'}],images=[str(self.image)]),'vision reply')
        self.assertEqual(commands[0][commands[0].index('--image')+1],str(self.image))
        self.assertIn('features.shell_tool=false',commands[0])
