"""Only runs inside the networkless media container. No shell, network or host paths."""
import json
from pathlib import Path
import struct
import wave
import zlib
import av


def png(frame,path):
    ratio=min(640/frame.width,640/frame.height,1)
    width,height=max(1,int(frame.width*ratio)),max(1,int(frame.height*ratio))
    rgb=frame.reformat(width=width,height=height,format='rgb24');plane=rgb.planes[0];raw=bytes(plane)
    body=b''.join(b'\0'+raw[row*plane.line_size:row*plane.line_size+width*3] for row in range(height))
    def chunk(name,data):return struct.pack('>I',len(data))+name+data+struct.pack('>I',zlib.crc32(name+data)&0xffffffff)
    path.write_bytes(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(body))+chunk(b'IEND',b''))


def decode():
    source='/input/video';out=Path('/output')
    with av.open(source) as container:
        if not container.streams.video:raise ValueError('No video stream')
        stream=container.streams.video[0];stream.thread_count=2
        duration=float(container.duration/av.time_base) if container.duration else float(stream.duration*stream.time_base) if stream.duration else 0
        if not 0<duration<=120 or stream.width*stream.height>16777216 or max(stream.width,stream.height)>4096:raise ValueError('Video bounds exceeded')
        samples=[]
        for index,timestamp in enumerate([0,duration/3,duration*2/3,max(0,duration-.1)]):
            container.seek(int(timestamp*av.time_base),backward=True,any_frame=False)
            selected=None
            for frame in container.decode(video=0):
                selected=frame
                if frame.time is None or frame.time>=timestamp:break
            if selected is None:continue
            name='frame-'+str(index)+'.png';png(selected,out/name)
            samples.append({'file':name,'seconds':round(float(selected.time),3) if selected.time is not None else None,'requested_seconds':round(timestamp,3)})
        if not samples:raise ValueError('No decoded frames')
        has_audio=bool(container.streams.audio)
    audio_seconds=0
    if has_audio:
        with av.open(source) as container,wave.open(str(out/'audio.wav'),'wb') as output:
            output.setnchannels(1);output.setsampwidth(2);output.setframerate(16000)
            resampler=av.AudioResampler(format='s16',layout='mono',rate=16000);count=0
            for frame in container.decode(audio=0):
                for converted in resampler.resample(frame):
                    size=min(converted.samples,960000-count)
                    output.writeframesraw(bytes(converted.planes[0])[:size*2]);count+=size
                if count>=960000:break
            audio_seconds=count/16000
    manifest={'duration_seconds':round(duration,3),'samples':samples,'audio_file':'audio.wav' if audio_seconds else None,'audio_seconds':audio_seconds,'method':'four sampled still frames; audio at most first 60 seconds'}
    (out/'metadata.json').write_text(json.dumps(manifest))
    print(json.dumps({'ok':True,'samples':len(samples)}))

try:decode()
except Exception:print(json.dumps({'ok':False,'error':'视频格式无法解码或超过受限时长/分辨率。'},ensure_ascii=False));raise SystemExit(1)
