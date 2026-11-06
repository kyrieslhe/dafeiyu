"""Original, fixed chat art only. Never lets model output select host files."""
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
import json
import shutil
import uuid

ROOT=Path(__file__).resolve().parent.parent
NAMES={'happy','curious','sleepy','cheer'}


def state(fish):
    row=fish.db.execute("SELECT value FROM settings WHERE key='expressions'").fetchone()
    value=json.loads(row['value']) if row else {'enabled':True,'day':'','count':0,'last':0}
    day=datetime.fromtimestamp(fish.clock(),ZoneInfo('Asia/Hong_Kong')).strftime('%Y-%m-%d')
    if value['day']!=day:value.update(day=day,count=0)
    return value


def prepare(fish,name):
    if name not in NAMES:raise ValueError('只支持内置原创表情。')
    value=state(fish)
    if not value['enabled'] or value['count']>=3 or fish.clock()-value['last']<900:return None
    source=ROOT/'assets/expressions'/(name+'.png')
    if not source.is_file() or source.is_symlink() or not source.read_bytes().startswith(b'\x89PNG\r\n\x1a\n'):return None
    directory=fish.home/'media/outbound';directory.mkdir(parents=True,exist_ok=True,mode=0o700)
    path=directory/(uuid.uuid4().hex+'.png');shutil.copyfile(source,path);path.chmod(0o600)
    return path


def accepted(fish):
    value=state(fish);value['count']+=1;value['last']=fish.clock()
    with fish.db:fish.db.execute("INSERT OR REPLACE INTO settings VALUES ('expressions',?)",(json.dumps(value),))


def command(fish,argument):
    value=state(fish)
    if argument:
        if argument not in ('on','off'):raise ValueError('用法：/expressions on 或 off')
        value['enabled']=argument=='on'
        with fish.db:fish.db.execute("INSERT OR REPLACE INTO settings VALUES ('expressions',?)",(json.dumps(value),))
    return {'enabled':value['enabled'],'accepted_today':value['count'],'daily_max':3,'minimum_interval_minutes':15,'note':'内置原创图片附件，不是原生微信收藏表情；发送接受不代表已读。'}
