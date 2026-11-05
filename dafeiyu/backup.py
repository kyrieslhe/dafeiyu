"""Authenticated encrypted snapshots via official age, never home-grown cryptography."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path,PurePosixPath
import shutil
import sqlite3
import subprocess
import tarfile
import tempfile
import time
import uuid
from zoneinfo import ZoneInfo
from . import __version__
from .core import Fish,ModelError


class BackupError(ModelError):pass


def binaries():
    root=Path(__file__).resolve().parent.parent
    age=Path(os.environ.get('DAFEIYU_AGE_BIN',str(root/'var/runtime/age/age')))
    keygen=age.with_name('age-keygen')
    if not age.is_file() or not keygen.is_file():raise BackupError('请先运行 python3 scripts/setup_age.py 安装固定 age 运行时。')
    return str(age),str(keygen)


def run(command):
    try:result=subprocess.run(command,capture_output=True,text=True,timeout=30)
    except (OSError,subprocess.TimeoutExpired):raise BackupError('age 进程失败或超时，未输出明文。') from None
    if result.returncode:raise BackupError('age 操作失败（密钥不匹配、文件被改动或格式错误），未应用恢复。')
    return result.stdout.strip()


def setup(home):
    home=Path(home).resolve();home.mkdir(mode=0o700,parents=True,exist_ok=True)
    age,keygen=binaries();secrets=home/'secrets'
    if secrets.is_symlink():raise BackupError('秘密目录不能是符号链接。')
    secrets.mkdir(mode=0o700,exist_ok=True);os.chmod(secrets,0o700)
    key=secrets/'recovery.agekey'
    if key.is_symlink():raise BackupError('恢复密钥不能是符号链接。')
    if not key.exists():
        if (secrets/'recipient.txt').exists() or any((home/'backups').glob('*.age')):
            raise BackupError('已有备份公钥但恢复密钥缺失；请找回原密钥，不会自动生成新密钥覆盖旧身份。')
        run([keygen,'-o',str(key)])
    os.chmod(key,0o600)
    recipient=run([keygen,'-y',str(key)])
    if not recipient.startswith('age1') or len(recipient)>200:raise BackupError('恢复公钥格式错误。')
    (secrets/'recipient.txt').write_text(recipient+'\n');os.chmod(secrets/'recipient.txt',0o600)
    fish=Fish(home)
    with fish.db:fish.db.execute("INSERT OR REPLACE INTO settings VALUES ('backup_enabled','1')")
    fish.close()
    return key


def snapshot(home):
    home=Path(home).resolve();age,_=binaries()
    recipient=home/'secrets/recipient.txt'
    if not recipient.is_file() or recipient.is_symlink():raise BackupError('尚未设置备份恢复密钥。')
    backups=home/'backups'
    if backups.is_symlink():raise BackupError('备份目录不能是符号链接。')
    backups.mkdir(mode=0o700,exist_ok=True);os.chmod(backups,0o700)
    with tempfile.TemporaryDirectory(prefix='.backup-',dir=home) as directory:
        temporary=Path(directory);database=temporary/'fish.sqlite'
        source=sqlite3.connect(str(home/'fish.sqlite'),timeout=15);target=sqlite3.connect(database)
        started=time.monotonic()
        def progress(*_):
            if time.monotonic()-started>20:raise BackupError('数据库快照超时。')
        try:source.backup(target,pages=100,progress=progress,sleep=.01)
        finally:source.close();target.close()
        files={'fish.sqlite':database};size=database.stat().st_size
        reports=home/'reports'
        if reports.is_symlink():raise BackupError('报告目录不能是符号链接。')
        if reports.exists():
            for path in reports.iterdir():
                if path.is_symlink():raise BackupError('报告含符号链接，拒绝打包。')
                if path.is_file() and path.suffix in ('.md','.json'):
                    size+=path.stat().st_size
                    if size>100000000:raise BackupError('备份超出 100MB 上限。')
                    frozen=temporary/'reports'/path.name;frozen.parent.mkdir(exist_ok=True)
                    frozen.write_bytes(path.read_bytes());files['reports/'+path.name]=frozen
        if len(files)>1000 or size>100000000:raise BackupError('备份超出 1000 文件或 100MB 上限。')
        manifest={'version':__version__,'created':datetime.now(timezone.utc).isoformat(),
                  'files':{name:hashlib.sha256(path.read_bytes()).hexdigest() for name,path in files.items()}}
        (temporary/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False))
        plain=temporary/'snapshot.tar.gz'
        with tarfile.open(plain,'w:gz') as archive:
            for name,path in files.items():archive.add(path,arcname=name,recursive=False)
            archive.add(temporary/'manifest.json',arcname='manifest.json')
        name='fish-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:6]+'.tar.gz.age'
        output=backups/(name+'.tmp')
        try:
            run([age,'-r',recipient.read_text().strip(),'-o',str(output),str(plain)])
            os.chmod(output,0o600);final=backups/name;output.replace(final)
        finally:output.unlink(missing_ok=True)
    for path in sorted(backups.glob('fish-*.tar.gz.age'))[:-14]:path.unlink()
    return final


def safe_members(archive):
    members=archive.getmembers()
    if len(members)>1001 or sum(x.size for x in members)>110000000:raise BackupError('恢复归档超出大小限制。')
    names=set()
    for member in members:
        path=PurePosixPath(member.name)
        if member.size<0 or not member.isfile() or path.is_absolute() or '..' in path.parts or '\\' in member.name:
            raise BackupError('恢复归档含非法路径或链接。')
        if member.name not in ('fish.sqlite','manifest.json') and not (len(path.parts)==2 and path.parts[0]=='reports' and path.suffix in ('.md','.json')):
            raise BackupError('恢复归档含非允许文件。')
        if member.name in names:raise BackupError('恢复归档含重复文件。')
        names.add(member.name)
    if not {'fish.sqlite','manifest.json'}<=names:raise BackupError('恢复归档缺少数据库或清单。')
    return members


def restore(home,encrypted,target,key=None):
    home=Path(home).resolve();target=Path(target).absolute();age,_=binaries()
    if target.is_symlink() or target.exists():raise BackupError('恢复目标必须是全新的目录，避免覆盖现有数据。')
    key=Path(key) if key else home/'secrets/recovery.agekey'
    if not key.is_file() or key.is_symlink():raise BackupError('找不到有效的恢复密钥文件。')
    tombstones=[]
    if (home/'fish.sqlite').is_file():
        current=sqlite3.connect('file:'+str(home/'fish.sqlite')+'?mode=ro',uri=True)
        try:
            if current.execute("SELECT count(*) FROM sqlite_master WHERE name='memory_tombstones'").fetchone()[0]:
                tombstones=list(current.execute('SELECT normalized,deleted FROM memory_tombstones'))
        finally:current.close()
    with tempfile.TemporaryDirectory(prefix='.restore-',dir=home) as directory:
        temporary=Path(directory);plain=temporary/'snapshot.tar.gz'
        run([age,'-d','-i',str(key),'-o',str(plain),str(Path(encrypted).resolve())])
        if plain.stat().st_size>110000000:raise BackupError('解密后的归档过大。')
        content=temporary/'content';content.mkdir()
        with tarfile.open(plain,'r:gz') as archive:
            members=safe_members(archive)
            for member in members:
                path=content/member.name;path.parent.mkdir(parents=True,exist_ok=True)
                path.write_bytes(archive.extractfile(member).read());os.chmod(path,0o600)
        manifest=json.loads((content/'manifest.json').read_text())
        if not isinstance(manifest,dict) or not isinstance(manifest.get('files'),dict):raise BackupError('恢复清单格式错误。')
        actual={p.relative_to(content).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in content.rglob('*') if p.is_file() and p.name!='manifest.json'}
        if manifest.get('files')!=actual:raise BackupError('恢复文件哈希不匹配。')
        checked=sqlite3.connect(content/'fish.sqlite')
        try:
            if checked.execute('PRAGMA quick_check').fetchone()[0]!='ok':raise BackupError('恢复数据库校验失败。')
            names={row[0] for row in checked.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not {'memories','tasks','outbox','settings'}<=names:raise BackupError('恢复文件不是有效的大肥鱼数据库。')
        finally:checked.close()
        # Only move validated content into a brand new private directory.
        target.parent.mkdir(parents=True,exist_ok=True);shutil.move(str(content),str(target));os.chmod(target,0o700)
    fish=Fish(target)
    try:
        from .memory import fingerprint
        deleted={value for value,_ in tombstones}
        for memory in fish.rows('SELECT id,content FROM memories'):
            if fingerprint(memory['content']) in deleted:fish.forget(memory['id'])
        with fish.db:
            fish.db.executemany('INSERT OR IGNORE INTO memory_tombstones VALUES (?,?)',tombstones)
            fish.db.execute("UPDATE settings SET value='1' WHERE key='paused'")
            fish.db.execute("INSERT OR REPLACE INTO settings VALUES ('backup_enabled','0')")
            fish.db.execute("UPDATE tasks SET state='failed',error='从备份恢复的在途任务，不自动重放' WHERE state IN ('running','applying')")
            if fish.db.execute("SELECT count(*) FROM sqlite_master WHERE name='channel_binding'").fetchone()[0]:fish.db.execute('UPDATE channel_binding SET last_seen=0')
            if fish.db.execute("SELECT count(*) FROM sqlite_master WHERE name='deliveries'").fetchone()[0]:fish.db.execute("UPDATE deliveries SET state='delivery_unknown' WHERE state='sending'")
    finally:fish.close()
    return target


def maybe_backup(fish):
    enabled=fish.db.execute("SELECT value FROM settings WHERE key='backup_enabled'").fetchone()
    if not enabled or enabled[0]!='1':return None
    day=datetime.fromtimestamp(fish.clock(),ZoneInfo('Asia/Hong_Kong')).strftime('%Y-%m-%d')
    done=fish.db.execute("SELECT value FROM settings WHERE key='last_backup_day'").fetchone()
    retry=fish.db.execute("SELECT value FROM settings WHERE key='backup_retry_at'").fetchone()
    if done and done[0]==day or retry and float(retry[0])>fish.clock():return None
    try:
        path=snapshot(fish.home)
        with fish.db:fish.db.execute("INSERT OR REPLACE INTO settings VALUES ('last_backup_day',?)",(day,))
        return path.name
    except (BackupError,OSError,sqlite3.Error):
        with fish.db:
            fish.db.execute("INSERT OR REPLACE INTO settings VALUES ('backup_retry_at',?)",(str(fish.clock()+3600),))
            fish.db.execute('INSERT INTO audit(action,resource,created) VALUES (?,?,?)',('backup_failed','local_encrypted_snapshot',fish.clock()))
        return None


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--home',default='var')
    sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('setup');sub.add_parser('create')
    command=sub.add_parser('restore');command.add_argument('archive');command.add_argument('--target',required=True);command.add_argument('--key')
    args=parser.parse_args()
    try:
        if args.command=='setup':print('恢复密钥已保存到本机私密文件（请单独保管）：',setup(args.home))
        elif args.command=='create':print(snapshot(args.home))
        else:print('已恢复到新目录；所有自主任务保持暂停：',restore(args.home,args.archive,args.target,args.key))
    except (BackupError,OSError,ValueError,tarfile.TarError,sqlite3.Error) as error:
        print(str(error) if isinstance(error,BackupError) else '备份或恢复失败；未覆盖原数据。',file=__import__('sys').stderr);raise SystemExit(1)

if __name__=='__main__':main()
