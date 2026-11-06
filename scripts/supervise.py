#!/usr/bin/env python3
"""User-session watchdog; no model calls, global power changes or hidden retries."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import urllib.request

ROOT=Path(__file__).resolve().parent.parent
running=True


def stop(_signum,_frame):
    global running
    running=False


class RecoveryPolicy:
    """Three failed health checks; at most three repairs in ten minutes."""
    def __init__(self):
        self.failures=[]
        self.bad=0
        self.last_wall=None
        self.last_repair=None

    def observe(self,processes_ok,gateway_ok,channel_ok,now,wall):
        resumed=self.last_wall is not None and wall-self.last_wall>120
        self.last_wall=wall
        self.bad=0 if gateway_ok and channel_ok else self.bad+1
        action='start' if not processes_ok else 'restart'
        reason='missing-process' if not processes_ok else ('host-resume' if resumed else 'unhealthy')
        if processes_ok and not resumed and self.bad<3:return None
        if self.last_repair is not None and now-self.last_repair<60:return None
        self.failures=[when for when in self.failures if now-when<600]
        if len(self.failures)>=3:return ('pause','repair-budget')
        self.failures.append(now);self.last_repair=now;self.bad=0
        return (action,reason)


def probe():
    """No idle-inbound timeout: silence is not a broken channel."""
    try:
        with urllib.request.urlopen('http://127.0.0.1:18791/health',timeout=3) as response:
            gateway_ok=response.status==200
    except OSError:return False,False
    try:
        result=subprocess.run([str(ROOT/'scripts/openclaw'),'channels','status','--json'],capture_output=True,text=True,timeout=15)
        value=json.loads(result.stdout)
        accounts=value.get('channelAccounts',{}).get('openclaw-weixin',[])
        if not isinstance(accounts,list) or not all(isinstance(account,dict) for account in accounts):return gateway_ok,False
        # Disabled/unconfigured channels are deliberate configuration, not repair targets.
        channel_ok=result.returncode==0 and all(account.get('running') for account in accounts if account.get('enabled') and account.get('configured'))
        return gateway_ok,channel_ok
    except (OSError,ValueError,AttributeError,subprocess.TimeoutExpired):return gateway_ok,False


def awake_command(pid):
    # -s applies only on AC power; no display assertion, pmset mutation or lid bypass.
    return ['/usr/bin/caffeinate','-s','-w',str(pid)]


def release_awake(process):
    if process is not None and process.poll() is None:
        process.terminate()
        try:process.wait(timeout=3)
        except subprocess.TimeoutExpired:process.kill();process.wait(timeout=3)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--keep-awake',action='store_true');args=parser.parse_args()
    (ROOT/'var').mkdir(mode=0o700,exist_ok=True)
    with (ROOT/'var/supervisor.lock').open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise SystemExit('已有本项目监管进程，未重复启动。')
        return supervise(args.keep_awake)


def supervise(keep_awake):
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    receipt=ROOT/'var/supervisor.json'
    stamp=subprocess.run(['ps','-p',str(os.getpid()),'-o','lstart='],capture_output=True,text=True,check=True).stdout.strip()
    receipt.write_text(json.dumps({'pid':os.getpid(),'stamp':stamp,'keep_awake':keep_awake,'started':time.time()}));receipt.chmod(0o600)
    policy=RecoveryPolicy();awake=None
    try:
        while running:
            paused=(ROOT/'var/services.paused').exists()
            if keep_awake and sys.platform=='darwin' and not paused:
                if awake is None or awake.poll() is not None:
                    awake=subprocess.Popen(awake_command(os.getpid()),stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            else:
                release_awake(awake);awake=None
            if not paused:
                try:
                    status=subprocess.run([sys.executable,str(ROOT/'scripts/services.py'),'status'],capture_output=True,text=True,timeout=10)
                    states=json.loads(status.stdout)
                    processes_ok=status.returncode==0 and isinstance(states,dict) and {'gateway','worker'}.issubset(states) and all(value=='running' for value in states.values())
                except (OSError,ValueError,subprocess.TimeoutExpired):processes_ok=False
                gateway_ok,channel_ok=probe() if processes_ok else (False,False)
                decision=policy.observe(processes_ok,gateway_ok,channel_ok,time.monotonic(),time.time())
                if decision:
                    action,reason=decision
                    print('Watchdog: '+action+' ('+reason+')',flush=True)
                    if action=='pause':
                        (ROOT/'var/services.paused').touch()
                        release_awake(awake);awake=None
                    elif running:
                        try:subprocess.run([sys.executable,str(ROOT/'scripts/services.py'),action,'--internal'],timeout=45,check=False)
                        except (OSError,subprocess.TimeoutExpired):print('Repair did not finish; bounded retry policy remains active.',flush=True)
            else:
                # An explicit start gets a fresh observation, not an old wake-gap restart.
                policy=RecoveryPolicy();policy.last_wall=time.time()
            for _ in range(30):
                if not running:break
                time.sleep(1)
    finally:
        release_awake(awake)
        try:subprocess.run([sys.executable,str(ROOT/'scripts/services.py'),'stop','--internal'],timeout=20,check=False)
        finally:receipt.unlink(missing_ok=True)

if __name__=='__main__':main()
