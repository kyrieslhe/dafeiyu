#!/usr/bin/env python3
"""Start/stop a detached watchdog for this login session, without installing an OS job."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parent.parent


def current():
    try:
        entry=json.loads((ROOT/'var/supervisor.json').read_text())
        result=subprocess.run(['ps','-p',str(entry['pid']),'-o','lstart='],capture_output=True,text=True,timeout=5)
        if entry.get('stamp') and entry['stamp']==result.stdout.strip():return entry
    except (OSError,ValueError,KeyError,TypeError,subprocess.TimeoutExpired):pass
    return None


def control(action,keep_awake=False):
    entry=current()
    if action=='status':
        print(json.dumps({'supervisor':'running' if entry else 'stopped','keep_awake_on_ac_configured':bool(entry and entry.get('keep_awake')),'services_paused':(ROOT/'var/services.paused').exists(),'scope':'current-login-session'},indent=2));return
    if action=='stop':
        # Stop marker is written first, so a concurrent watchdog cannot restart services.
        subprocess.run([sys.executable,str(ROOT/'scripts/services.py'),'stop'],check=True,timeout=30)
        if entry:
            os.kill(entry['pid'],signal.SIGTERM)
            for _ in range(100):
                if not current():break
                time.sleep(.1)
            else:raise SystemExit('监管进程仍在停止中；没有强制杀死不明进程。')
        print('本次登录的常驻已停止，保持唤醒请求已释放。');return
    if entry:
        if bool(entry.get('keep_awake'))!=keep_awake:
            raise SystemExit('监管进程已运行但保持唤醒选项不同。请先 stop，再按所需选项 start。')
        print('已有常驻监管进程，未重复启动。');return
    command=[sys.executable,str(ROOT/'scripts/supervise.py')]
    if keep_awake:command.append('--keep-awake')
    (ROOT/'var/services.paused').unlink(missing_ok=True)
    with (ROOT/'var/service-supervisor.log').open('ab') as log:
        process=subprocess.Popen(command,cwd=ROOT,stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
    for _ in range(100):
        if process.poll() is not None:raise SystemExit('监管进程启动失败，请检查私人 service-supervisor.log。')
        if current():
            print('当前登录会话的监管已启动；健康检查及服务恢复正在后台运行。');return
        time.sleep(.1)
    raise SystemExit('尚未确认监管进程启动；请查看 status 和私人日志，未宣称就绪。')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['start','stop','status']);parser.add_argument('--keep-awake',action='store_true',help='仅 macOS 接电时防止系统休眠，允许屏幕休眠');args=parser.parse_args()
    (ROOT/'var').mkdir(mode=0o700,exist_ok=True)
    with (ROOT/'var/stay-online.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        control(args.action,args.keep_awake)

if __name__=='__main__':main()
