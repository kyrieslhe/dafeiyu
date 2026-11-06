"""Small local health observation, never a delivery receipt or uptime guarantee."""
import json
import os
from pathlib import Path
import tempfile


def record(home,value):
    allowed={key:value.get(key) for key in ('sampled_at','processes_ok','gateway_ok','channel_ok','paused','gap_seconds','repair')}
    directory=Path(home);directory.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix='.health-',dir=directory)
    try:
        with os.fdopen(fd,'w') as stream:json.dump(allowed,stream)
        os.replace(name,directory/'runtime-health.json')
    finally:
        if os.path.exists(name):os.unlink(name)


def summary(home,now):
    try:
        path=Path(home)/'runtime-health.json'
        if path.is_symlink() or path.stat().st_size>4096:raise ValueError()
        raw=json.loads(path.read_text());result={k:raw.get(k) for k in ('sampled_at','processes_ok','gateway_ok','channel_ok','paused','gap_seconds','repair')}
        result['age_seconds']=round(max(0,now-result['sampled_at']),1);result['fresh']=result['age_seconds']<120
        result['note']='本机采样，不代表微信送达或已读；过期采样不视为当前在线。'
        return result
    except (OSError,ValueError,TypeError):return {'fresh':False,'note':'没有可用的当前健康采样。'}
