#!/usr/bin/env python3
"""Manage only this project's gateway/worker, using PID plus process start time."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parent.parent
STATE=ROOT/'var/services.json'

def stamp(pid):
    result=subprocess.run(['ps','-p',str(pid),'-o','lstart='],capture_output=True,text=True)
    return result.stdout.strip() if result.returncode==0 else ''

def state():
    try:return json.loads(STATE.read_text())
    except (OSError,ValueError):return {}

def active(entry):return bool(entry.get('stamp')) and stamp(entry['pid'])==entry['stamp']

def main():
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['start','stop','status','restart']);args=parser.parse_args()
    records=state()
    if args.action in ('stop','restart'):
        for name,entry in records.items():
            if active(entry):
                (os.kill if entry.get('adopted') else os.killpg)(entry['pid'],signal.SIGTERM)
                end=time.monotonic()+5
                while active(entry) and time.monotonic()<end:time.sleep(.1)
                if active(entry):(os.kill if entry.get('adopted') else os.killpg)(entry['pid'],signal.SIGKILL)
        STATE.unlink(missing_ok=True);records={}
    if args.action in ('start','restart'):
        commands={'gateway':[str(ROOT/'scripts/openclaw'),'gateway','run'],
                  'worker':[sys.executable,'-m','dafeiyu','--home',str(ROOT/'var'),'worker','--deliver']}
        for name,command in commands.items():
            if name=='gateway' and name not in records:
                found=subprocess.run(['lsof','-t','-iTCP:18791','-sTCP:LISTEN'],capture_output=True,text=True)
                if found.stdout.strip():
                    pid=int(found.stdout.strip().splitlines()[0])
                    cwd=subprocess.run(['lsof','-a','-p',str(pid),'-d','cwd','-Fn'],capture_output=True,text=True).stdout
                    if '\nn'+str(ROOT)+'\n' not in cwd:raise SystemExit('18791 端口被其他程序占用，未触碰该程序。')
                    records[name]={'pid':pid,'stamp':stamp(pid),'adopted':True}
            if name in records and active(records[name]):continue
            env=dict(os.environ)
            env['PATH']='/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS:'+env.get('PATH','')
            with open(ROOT/'var'/('service-'+name+'.log'),'ab') as log:
                process=subprocess.Popen(command,cwd=ROOT,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
            time.sleep(.2)
            records[name]={'pid':process.pid,'stamp':stamp(process.pid)}
        STATE.write_text(json.dumps(records));os.chmod(STATE,0o600)
    print(json.dumps({name:('running' if active(entry) else 'stopped') for name,entry in records.items()},indent=2))

if __name__=='__main__':main()
