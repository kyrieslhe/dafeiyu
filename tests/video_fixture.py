"""Generate a tiny original silent clip inside the installed networkless codec image."""
from pathlib import Path
import subprocess

CODE='''import av
from fractions import Fraction
output=av.open('/output/clip.mp4','w')
stream=output.add_stream('mpeg4',rate=10)
stream.width=160;stream.height=96;stream.pix_fmt='yuv420p'
for index in range(30):
    frame=av.VideoFrame(160,96,'yuv420p');frame.pts=index;frame.time_base=Fraction(1,10)
    for plane,value in zip(frame.planes,(41,240,110)):plane.update(bytes([value])*plane.buffer_size)
    for packet in stream.encode(frame):output.mux(packet)
for packet in stream.encode():output.mux(packet)
output.close()
'''


def create_clip(directory,runtime,audio=False):
    directory=Path(directory).resolve();directory.mkdir(parents=True,exist_ok=True);directory.chmod(0o777)
    image=(Path(runtime)/'image-id.txt').read_text().strip()
    subprocess.run(['docker','run','--rm','--network=none','--read-only','--cap-drop=ALL','--security-opt','no-new-privileges','--user','65534:65534','--memory','256m','--cpus','1','--pids-limit','64',
                    '--mount','type=bind,source='+str(directory)+',target=/output','--entrypoint','python',image,'-c',AUDIO_CODE if audio else CODE],check=True,capture_output=True,timeout=20)
    return directory/'clip.mp4'

AUDIO_CODE=CODE.replace("stream.width=", "audio=output.add_stream('aac',rate=16000)\nstream.width=").replace("output.close()", """
import math,struct
for start in range(0,48000,1024):
    size=min(1024,48000-start)
    frame=av.AudioFrame(format='s16',layout='mono',samples=size)
    frame.sample_rate=16000;frame.pts=start;frame.time_base=Fraction(1,16000)
    frame.planes[0].update(struct.pack('<'+'h'*size,*[int(8000*math.sin(2*math.pi*440*i/16000)) for i in range(start,start+size)]))
    for packet in audio.encode(frame):output.mux(packet)
for packet in audio.encode():output.mux(packet)
output.close()""")
