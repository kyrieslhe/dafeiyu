"""Read-only official Codex account limits. Never purchases credits or consumes resets."""
import json
import os
import select
import signal
import subprocess
import tempfile
import time
from .core import Model


def summarize(value):
    buckets=value.get('rateLimitsByLimitId') or {}
    bucket=buckets.get('codex') or value.get('rateLimits') or {}
    windows={};unknown=False;resets=[]
    for name in ('primary','secondary'):
        window=bucket.get(name)
        used=window.get('usedPercent') if isinstance(window,dict) else None
        if not isinstance(used,(int,float)) or isinstance(used,bool) or not 0<=used<=100:unknown=True;continue
        windows[name]=100-used
        reset=window.get('resetsAt')
        if isinstance(reset,(int,float)):resets.append(reset)
    status='low' if any(remaining<10 for remaining in windows.values()) or bucket.get('spendControlReached') or value.get('spendControlReached') or bucket.get('rateLimitReachedType') else 'unknown' if unknown or not windows else 'ok'
    return {'status':status,'remaining':windows,'next_reset':min(resets) if resets else None}


def read(codex):
    if not codex:return {'status':'unknown','remaining':{},'next_reset':None}
    child=None
    try:
        with tempfile.TemporaryDirectory(prefix='fish-quota-') as cwd:
            child=subprocess.Popen([codex,'app-server','--listen','stdio://'],cwd=cwd,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,start_new_session=True,bufsize=0)
            def send(value):child.stdin.write((json.dumps(value)+'\n').encode());child.stdin.flush()
            send({'id':0,'method':'initialize','params':{'clientInfo':{'name':'dafeiyu_quota','version':'0.1.0'}}})
            buffer=b'';started=time.monotonic()
            while time.monotonic()-started<8:
                readable,_,_=select.select([child.stdout],[],[],.1)
                if not readable:continue
                data=os.read(child.stdout.fileno(),65536)
                if not data:break
                buffer+=data
                if len(buffer)>100000:break
                while b'\n' in buffer:
                    line,buffer=buffer.split(b'\n',1)
                    try:item=json.loads(line)
                    except ValueError:continue
                    if item.get('id')==0:
                        if 'error' in item:return {'status':'unknown','remaining':{},'next_reset':None}
                        send({'method':'initialized','params':{}})
                        send({'id':1,'method':'account/rateLimits/read'})
                    elif item.get('id')==1:
                        return summarize(item.get('result') or {})
    except (OSError,ValueError,TypeError,AttributeError):pass
    finally:
        if child:
            if child.stdin:child.stdin.close()
            try:child.wait(timeout=1)
            except subprocess.TimeoutExpired:
                try:os.killpg(child.pid,signal.SIGTERM)
                except ProcessLookupError:pass
                try:child.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    try:os.killpg(child.pid,signal.SIGKILL)
                    except ProcessLookupError:pass
                    child.wait(timeout=2)
            if child.stdout:child.stdout.close()
    return {'status':'unknown','remaining':{},'next_reset':None}


def guard(fish,max_age=60,reader=read):
    if not isinstance(fish.model,Model):return {'status':'ok','remaining':{},'checked_at':fish.clock(),'source':'test model'}
    if fish.model.provider!='codex':return {'status':'unknown','remaining':{},'checked_at':fish.clock(),'source':'no Codex limits'}
    row=fish.db.execute("SELECT value FROM settings WHERE key='autonomy_quota'").fetchone()
    if row:
        try:
            cached=json.loads(row['value'])
            if 0<=fish.clock()-cached['checked_at']<max_age:return cached
        except (ValueError,KeyError,TypeError):pass
    value=reader(fish.model.codex);value['checked_at']=fish.clock();value['source']='official Codex account/rateLimits/read'
    with fish.db:fish.db.execute("INSERT OR REPLACE INTO settings VALUES ('autonomy_quota',?)",(json.dumps(value),))
    return value
