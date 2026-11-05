#!/usr/bin/env python3
"""Build an offline codec image from a pinned base and hash-checked binary wheel."""
import hashlib
import json
from pathlib import Path
import platform
import shutil
import subprocess
import urllib.request

ROOT=Path(__file__).resolve().parent.parent


def install(runtime=None):
    runtime=Path(runtime or ROOT/'var/video-runtime').resolve();runtime.mkdir(mode=0o700,parents=True,exist_ok=True)
    data=json.loads((ROOT/'integrations/video/wheels.json').read_text());arch='aarch64' if platform.machine() in ('arm64','aarch64') else 'x86_64'
    wheel=data['wheels'][arch];asset=runtime/wheel['name']
    if not asset.exists() or hashlib.sha256(asset.read_bytes()).hexdigest()!=wheel['sha256']:
        temporary=asset.with_suffix('.part')
        try:
            with urllib.request.urlopen(wheel['url'],timeout=30) as source,temporary.open('wb') as out:
                count=0
                while True:
                    chunk=source.read(1024*1024)
                    if not chunk:break
                    count+=len(chunk)
                    if count>wheel['size']:raise ValueError('Codec wheel exceeded expected size')
                    out.write(chunk)
            if temporary.stat().st_size!=wheel['size'] or hashlib.sha256(temporary.read_bytes()).hexdigest()!=wheel['sha256']:raise ValueError('Codec wheel integrity failed')
            temporary.replace(asset)
        finally:temporary.unlink(missing_ok=True)
    for name in ('Dockerfile','decode.py'):shutil.copyfile(ROOT/'integrations/video'/name,runtime/name)
    manifest=json.loads((ROOT/'integrations/video/runtime.json').read_text())
    subprocess.run(['docker','pull',manifest['base_image']],check=True)
    identifier=runtime/'image-id.txt'
    subprocess.run(['docker','build','--network=none','--pull=false','--iidfile',str(identifier),str(runtime)],check=True)
    (runtime/'build.json').write_text(json.dumps({'decoder_sha256':hashlib.sha256((runtime/'decode.py').read_bytes()).hexdigest(),'wheel_sha256':wheel['sha256'],'base_image':manifest['base_image']}))
    print('短视频解码镜像已固定构建；运行时不联网，不挂载用户凭据。')
    return runtime

if __name__=='__main__':install()
