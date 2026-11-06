#!/usr/bin/env python3
"""Install pinned official runtimes into ignored project-local storage; preserve existing auth."""
import hashlib
import json
import os
from pathlib import Path
import platform
import secrets
import shutil
import subprocess
import sys
import tarfile
import urllib.request

ROOT=Path(__file__).resolve().parent.parent
RUNTIME=ROOT/'var/runtime'
VERSION='v26.13.0'

def distribution(system,machine):
    systems={'Darwin':'darwin','Linux':'linux'};architectures={'arm64':'arm64','aarch64':'arm64','x86_64':'x64','AMD64':'x64'}
    if system not in systems or machine not in architectures:raise ValueError('运行时安装支持 macOS/Linux 的 arm64 或 x64。')
    return systems[system],architectures[machine]


def main():
    system,arch=distribution(platform.system(),platform.machine())
    RUNTIME.mkdir(parents=True,exist_ok=True)
    name=f'node-{VERSION}-{system}-{arch}'
    installed=RUNTIME/name
    if not installed.exists():
        archive=RUNTIME/(name+'.tar.gz');base=f'https://nodejs.org/dist/{VERSION}/'
        urllib.request.urlretrieve(base+archive.name,archive)
        checks=urllib.request.urlopen(base+'SHASUMS256.txt').read().decode()
        expected=next(line.split()[0] for line in checks.splitlines() if line.endswith('  '+archive.name))
        if hashlib.sha256(archive.read_bytes()).hexdigest()!=expected:raise SystemExit('Node 校验失败')
        with tarfile.open(archive) as contents:
            for member in contents:
                dest=(RUNTIME/member.name).resolve()
                if not dest.is_relative_to(installed.resolve()) or not (member.isfile() or member.isdir() or member.issym() or member.islnk()):raise SystemExit('非法归档路径或类型')
                if member.issym() or member.islnk():
                    target=((dest.parent/member.linkname) if member.issym() else (RUNTIME/member.linkname)).resolve()
                    if not target.is_relative_to(installed.resolve()):raise SystemExit('非法归档链接')
            contents.extractall(RUNTIME)
    link=RUNTIME/'node'
    if link.is_symlink() and link.resolve()!=installed.resolve():link.unlink()
    if not link.exists():link.symlink_to(installed.name,target_is_directory=True)
    elif not link.is_symlink():raise SystemExit('node 路径不是本项目管理的链接，未覆盖。')
    destination=ROOT/'var/openclaw';destination.mkdir(parents=True,exist_ok=True)
    for name in ['package.json','package-lock.json']:shutil.copyfile(ROOT/'integrations/runtime'/name,destination/name)
    vendor=destination/'vendor';vendor.mkdir(exist_ok=True)
    metadata=json.loads((ROOT/'integrations/runtime/vendor/provenance.json').read_text())
    archive=ROOT/'integrations/runtime/vendor/npm-12.2.2-dafeiyu.1.tgz'
    if hashlib.sha256(archive.read_bytes()).hexdigest()!=metadata['sha256']:raise SystemExit('本地 npm 安全修补包校验失败')
    shutil.copyfile(archive,vendor/archive.name)
    shutil.copyfile(ROOT/'integrations/runtime/vendor/provenance.json',vendor/'provenance.json')
    env=dict(os.environ);env['PATH']=str(link/'bin')+os.pathsep+env.get('PATH','')
    subprocess.run([str(link/'bin/npm'),'ci','--ignore-scripts','--prefix',str(destination)],env=env,check=True)
    state=ROOT/'var/gateway';state.mkdir(mode=0o700,exist_ok=True)
    path=state/'openclaw.json'
    if not path.exists():
        config={'gateway':{'mode':'local','bind':'loopback','port':18791,'auth':{'mode':'token','token':secrets.token_urlsafe(32)}},
            'plugins':{'allow':['openclaw-weixin','dafeiyu-bridge'],'load':{'paths':[str(destination/'node_modules/@tencent-weixin/openclaw-weixin'),str(ROOT/'integrations/openclaw')]},
             'entries':{'openclaw-weixin':{'enabled':True},'dafeiyu-bridge':{'enabled':True,'config':{'python':sys.executable,'project':str(ROOT),'home':str(ROOT/'var')}}}},
            'channels':{'openclaw-weixin':{'enabled':True}},'session':{'dmScope':'per-account-channel-peer'}}
        path.write_text(json.dumps(config,ensure_ascii=False,indent=2));os.chmod(path,0o600)
    print('运行时安装完成。已有配置及登录凭据保持不变。')

if __name__=='__main__':main()
