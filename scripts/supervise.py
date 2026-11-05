#!/usr/bin/env python3
"""User-session supervisor. It never calls a model or overrides an explicit stop."""
import json
from pathlib import Path
import signal
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parent.parent
running=True

def stop(_signum,_frame):
    global running
    running=False


def main():
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    failures=[]
    try:
        while running:
            paused=(ROOT/'var/services.paused').exists()
            if not paused:
                status=subprocess.run([sys.executable,str(ROOT/'scripts/services.py'),'status'],capture_output=True,text=True,timeout=20)
                try:states=json.loads(status.stdout)
                except ValueError:states={}
                if len(states)!=2 or any(value!='running' for value in states.values()):
                    failures=[when for when in failures if time.monotonic()-when<600]
                    if len(failures)>=3:
                        (ROOT/'var/services.paused').touch()
                        print('Repeated service failures; paused. Use services.py start after checking local logs.',flush=True)
                    else:
                        failures.append(time.monotonic())
                        subprocess.run([sys.executable,str(ROOT/'scripts/services.py'),'start','--internal'],timeout=45,check=False)
            for _ in range(30):
                if not running:break
                time.sleep(1)
    finally:
        subprocess.run([sys.executable,str(ROOT/'scripts/services.py'),'stop','--internal'],timeout=20,check=False)

if __name__=='__main__':main()
