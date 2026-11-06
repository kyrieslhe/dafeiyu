"""Verified code snapshots; private data stays in the original var directory."""
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import tempfile


def write(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(dir=path.parent,prefix='.deploy-')
    try:
        with os.fdopen(fd,'w') as stream:stream.write(json.dumps(value,ensure_ascii=False));stream.flush();os.fsync(stream.fileno())
        os.replace(name,path)
    finally:
        if os.path.exists(name):os.unlink(name)


def verify(root,commit):
    if not isinstance(commit,str) or not re.fullmatch('[0-9a-f]{40}',commit):raise ValueError('版本编号无效。')
    root=Path(root).resolve();release=root/'var/releases'/commit
    if release.is_symlink() or not release.is_dir():raise ValueError('版本目录不可用。')
    receipt=json.loads((release/'release.json').read_text())
    if receipt.get('commit')!=commit:raise ValueError('版本记录不一致。')
    for name,digest in receipt['files'].items():
        path=release/name
        if '..' in Path(name).parts or not path.is_relative_to(release) or path.is_symlink() or any(p.is_symlink() for p in path.parents if p!=release and p.is_relative_to(release)):raise ValueError('版本路径异常。')
        if hashlib.sha256(path.read_bytes()).hexdigest()!=digest:raise ValueError('版本文件已改变，请重新准备。')
    if (release/'var').resolve()!=root/'var':raise ValueError('版本私人数据目录异常。')
    return release


def selected(root):
    root=Path(root).resolve();receipt=root/'var/active-release.json'
    return verify(root,json.loads(receipt.read_text())['commit']) if receipt.exists() else root


def prepare(root):
    root=Path(root).resolve()
    def git(*args):return subprocess.check_output(['git',*args],cwd=root)
    if git('status','--porcelain','--untracked-files=no').strip():raise ValueError('请先保存已跟踪文件的修改。')
    commit=git('rev-parse','HEAD').decode().strip()
    if commit!=git('rev-parse','origin/main').decode().strip():raise ValueError('仅准备已同步 origin/main 的提交。')
    destination=root/'var/releases'/commit
    if destination.exists():return verify(root,commit)
    destination.parent.mkdir(parents=True,exist_ok=True)
    temporary=Path(tempfile.mkdtemp(prefix='.prepare-',dir=destination.parent))
    files={}
    try:
        with tarfile.open(fileobj=io.BytesIO(git('archive','--format=tar',commit))) as archive:
            for member in archive:
                path=temporary/member.name
                if not path.is_relative_to(temporary) or '..' in Path(member.name).parts or Path(member.name).parts[0] in ('var','.git') or not (member.isfile() or member.isdir()):raise ValueError('归档包含不允许的路径。')
                if member.isdir():path.mkdir(parents=True,exist_ok=True);continue
                path.parent.mkdir(parents=True,exist_ok=True);data=archive.extractfile(member).read();path.write_bytes(data)
                path.chmod(0o555 if member.mode&0o111 else 0o444);files[member.name]=hashlib.sha256(data).hexdigest()
        (temporary/'var').symlink_to(root/'var',target_is_directory=True)
        write(temporary/'release.json',{'commit':commit,'files':files})
        temporary.rename(destination)
        return verify(root,commit)
    finally:
        if temporary.exists():shutil.rmtree(temporary)


def configure(config,release,root):
    # Modify code locations only; never export auth or duplicate a state directory.
    plugins=config['plugins'];entry=plugins['entries']['dafeiyu-bridge']['config']
    paths=plugins['load']['paths'];old=entry['project']
    plugins['load']['paths']=[str(release/'integrations/openclaw') if p==str(Path(old)/'integrations/openclaw') else p for p in paths]
    if str(release/'integrations/openclaw') not in plugins['load']['paths']:raise ValueError('未找到当前桥接插件路径，未切换。')
    entry['project']=str(release);entry['home']=str(root/'var')
    return config
