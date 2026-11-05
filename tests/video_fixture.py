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


def create_clip(directory,runtime):
    directory=Path(directory).resolve();directory.mkdir(parents=True,exist_ok=True);directory.chmod(0o777)
    image=(Path(runtime)/'image-id.txt').read_text().strip()
    subprocess.run(['docker','run','--rm','--network=none','--read-only','--cap-drop=ALL','--security-opt','no-new-privileges','--user','65534:65534','--memory','256m','--cpus','1','--pids-limit','64',
                    '--mount','type=bind,source='+str(directory)+',target=/output','--entrypoint','python',image,'-c',CODE],check=True,capture_output=True,timeout=20)
    return directory/'clip.mp4'
