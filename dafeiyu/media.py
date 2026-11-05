"""Bounded image custody. No remote URL fetching or arbitrary host-file access."""
from contextlib import contextmanager
import os
from pathlib import Path
import stat
import struct
import tempfile


class MediaError(ValueError):pass


def image_suffix(data):
    if data.startswith(b'\x89PNG\r\n\x1a\n'):
        if len(data)<33 or data[12:16]!=b'IHDR':raise MediaError('图片 PNG 头不完整。')
        width,height=struct.unpack('>II',data[16:24])
        if not 0<width<=10000 or not 0<height<=10000 or width*height>20000000:raise MediaError('图片分辨率过大，请缩小后重发。')
        return '.png'
    if data.startswith(b'\xff\xd8\xff') and data.endswith(b'\xff\xd9'):return '.jpg'
    raise MediaError('目前支持 PNG/JPEG 图片；请转换后再发。')


@contextmanager
def staged_images(home,items):
    if not isinstance(items,list) or not 1<=len(items)<=2:raise MediaError('一次最多处理两张图片。')
    home=Path(home).resolve()
    root=home/'gateway/media/inbound'
    staging=home/'media/staged';staging.mkdir(mode=0o700,parents=True,exist_ok=True)
    total=0
    with tempfile.TemporaryDirectory(prefix='image-',dir=staging) as directory:
        paths=[]
        for index,item in enumerate(items):
            if not isinstance(item,dict) or not isinstance(item.get('path'),str):raise MediaError('没有收到可读取的本地图片，请重新发送。')
            path=Path(item['path'])
            if not path.is_absolute() or path.resolve()!=path or not path.is_relative_to(root) or root.resolve()!=root:
                raise MediaError('附件不在微信入站媒体目录，未读取文件。')
            try:
                fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
                with os.fdopen(fd,'rb') as stream:
                    info=os.fstat(stream.fileno())
                    if not stat.S_ISREG(info.st_mode) or not 0<info.st_size<=8*1024*1024:raise MediaError('单张图片须为不超过 8MB 的普通文件。')
                    data=stream.read(8*1024*1024+1)
            except OSError:raise MediaError('图片已失效或无法读取，请重新发送。') from None
            total+=len(data)
            if len(data)>8*1024*1024 or total>12*1024*1024:raise MediaError('图片总大小超过 12MB，请压缩后重发。')
            target=Path(directory)/(str(index)+image_suffix(data));target.write_bytes(data);target.chmod(0o600);paths.append(str(target))
        yield paths


@contextmanager
def staged_audio(home,items):
    import io,wave
    if not isinstance(items,list) or len(items)!=1:raise MediaError('一次请发一条语音。')
    home=Path(home).resolve();root=home/'gateway/media/inbound';item=items[0]
    if not isinstance(item,dict) or not isinstance(item.get('path'),str):raise MediaError('没有收到本地语音附件。')
    path=Path(item['path'])
    if not path.is_absolute() or path.resolve()!=path or not path.is_relative_to(root) or root.resolve()!=root:raise MediaError('语音不在微信入站目录，未读取文件。')
    try:
        fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
        with os.fdopen(fd,'rb') as stream:
            info=os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or not 0<info.st_size<=12*1024*1024:raise MediaError('语音文件须小于 12MB。')
            data=stream.read(12*1024*1024+1)
        if len(data)>12*1024*1024:raise MediaError('语音文件过大。')
        with wave.open(io.BytesIO(data),'rb') as audio:
            duration=audio.getnframes()/audio.getframerate()
            if audio.getnchannels() not in (1,2) or not 8000<=audio.getframerate()<=48000 or not 0<duration<=60:raise MediaError('语音限 60 秒、单声道或双声道 WAV。')
    except (OSError,wave.Error,EOFError):raise MediaError('没有收到可解码的 WAV 语音；可先用微信转文字后发送。') from None
    staging=home/'media/staged';staging.mkdir(mode=0o700,parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='audio-',dir=staging) as directory:
        target=Path(directory)/'voice.wav';target.write_bytes(data);target.chmod(0o600)
        yield str(target)
