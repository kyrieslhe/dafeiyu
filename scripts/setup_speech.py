#!/usr/bin/env python3
"""Install optional offline ASR with pinned wheel and model integrity checks."""
import hashlib
import json
import platform
import tarfile
from pathlib import Path
import subprocess
import sys
import urllib.request
import venv

ROOT=Path(__file__).resolve().parent.parent


def verified(path,item):
    if not path.exists() or path.stat().st_size!=item['size']:return False
    algorithm=hashlib.sha256() if item.get('lfs') else hashlib.sha1(('blob '+str(item['size'])+'\0').encode())
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):algorithm.update(chunk)
    expected=item['lfs']['sha256'] if item.get('lfs') else item['blobId']
    return algorithm.hexdigest()==expected


def speech_python():
    if (3,12)<=sys.version_info[:2]<(3,14):return Path(sys.executable)
    manifest=json.loads((ROOT/'integrations/speech/python.json').read_text())
    if sys.platform!='darwin' or platform.machine()!='arm64':
        raise SystemExit('语音运行时需要 Python 3.12–3.13；此主机请用该版本执行 setup_speech.py。Mac arm64 会安装独立固定运行时。')
    target=ROOT/'var/runtime/speech-python';python=target/'python/bin/python3.12'
    if python.exists():return python
    target.mkdir(mode=0o700,parents=True,exist_ok=True);archive=target/'python.tar.gz'
    try:
        with urllib.request.urlopen(manifest['url'],timeout=30) as source,archive.open('wb') as stream:
            count=0
            while True:
                chunk=source.read(1024*1024)
                if not chunk:break
                count+=len(chunk)
                if count>manifest['size']:raise ValueError('Python archive exceeded size limit')
                stream.write(chunk)
        if archive.stat().st_size!=manifest['size'] or hashlib.sha256(archive.read_bytes()).hexdigest()!=manifest['sha256']:raise ValueError('Python archive integrity failed')
        with tarfile.open(archive) as contents:
            for member in contents:
                destination=(target/member.name).resolve()
                if not destination.is_relative_to(target):raise ValueError('Unsafe Python archive path')
                if member.issym() and not (destination.parent/member.linkname).resolve().is_relative_to(target):raise ValueError('Unsafe Python archive symlink')
                if member.islnk() and not (target/member.linkname).resolve().is_relative_to(target):raise ValueError('Unsafe Python archive hardlink')
                if member.isdev() or member.isfifo():raise ValueError('Unsupported Python archive member')
            contents.extractall(target)
    finally:archive.unlink(missing_ok=True)
    return python


def main():
    runtime=ROOT/'var/runtime/speech';runtime.parent.mkdir(parents=True,exist_ok=True)
    python=speech_python()
    if (runtime/'bin/python').exists():
        result=subprocess.run([str(runtime/'bin/python'),'-c','import sys;print(sys.version_info.minor)'],capture_output=True,text=True,check=True)
        if int(result.stdout)<12:raise SystemExit('已有旧版语音虚拟环境；请先保留并移走 var/runtime/speech，再重跑安装。不会自动覆盖环境。')
    else:subprocess.run([str(python),'-m','venv',str(runtime)],check=True)
    subprocess.run([str(runtime/'bin/python'),'-m','pip','install','--only-binary=:all:','--require-hashes','-r',str(ROOT/'integrations/speech/requirements.txt')],check=True)
    manifest=json.loads((ROOT/'integrations/speech/model.json').read_text())
    model=ROOT/'var/runtime/speech-model';model.mkdir(mode=0o700,parents=True,exist_ok=True)
    for item in manifest['files']:
        name=item['rfilename']
        if '/' in name or name.startswith('.'):raise SystemExit('Model manifest path rejected')
        target=model/name
        if verified(target,item):continue
        url='https://huggingface.co/'+manifest['repo']+'/resolve/'+manifest['revision']+'/'+name
        temporary=target.with_suffix(target.suffix+'.part')
        try:
            with urllib.request.urlopen(url,timeout=30) as source,temporary.open('wb') as destination:
                count=0
                while True:
                    chunk=source.read(1024*1024)
                    if not chunk:break
                    count+=len(chunk)
                    if count>item['size']:raise ValueError('Model download exceeded expected size')
                    destination.write(chunk)
            if not verified(temporary,item):raise ValueError('Model integrity verification failed')
            temporary.chmod(0o600);temporary.replace(target)
            print('Verified model asset: '+name,flush=True)
        finally:temporary.unlink(missing_ok=True)
    print('离线语音识别已安装；运行时只加载本地模型，不上传音频、不使用付费接口。')

if __name__=='__main__':main()
