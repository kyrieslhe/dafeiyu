#!/usr/bin/env python3
"""Manage only this project's systemd user unit. Never changes root/linger settings."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parent.parent
NAME='dafeiyu.service'


def quote(value):
    if any(ord(char)<32 for char in str(value)):raise ValueError('服务路径含控制字符。')
    return json.dumps(str(value).replace('%','%%'),ensure_ascii=False)


def definition(root=ROOT,python=sys.executable,home=None):
    root=Path(root).resolve();home=Path(home or Path.home())
    path=str(home/'.local/bin')+':'+str(home/'.npm-global/bin')+':/usr/local/bin:/usr/bin:/bin'
    return '\n'.join(['# Dafeiyu project: '+str(root),'[Unit]','Description=Dafeiyu private companion','StartLimitIntervalSec=600','StartLimitBurst=3','',
        '[Service]','Type=exec','WorkingDirectory='+quote(root),'ExecStart='+quote(python)+' '+quote(root/'scripts/supervise.py'),
        'Environment='+quote('PATH='+path),'UMask=0077','Restart=on-failure','RestartSec=15','TimeoutStopSec=45','KillMode=mixed','StandardOutput=journal','StandardError=journal','',
        '[Install]','WantedBy=default.target',''])


def main():
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['print','install','uninstall','status']);args=parser.parse_args()
    body=definition()
    if args.action=='print':print(body,end='');return
    if not sys.platform.startswith('linux'):raise SystemExit('本机不是 Linux；没有安装或更改任何启动项。')
    unit=Path.home()/'.config/systemd/user'/NAME
    marker='# Dafeiyu project: '+str(ROOT)
    if unit.exists() and unit.read_text().splitlines()[0]!=marker:raise SystemExit('同名服务属于其他目录，未覆盖。')
    def run(*arguments,check=False):return subprocess.run(['systemctl','--user',*arguments],capture_output=True,text=True,timeout=50,check=check)
    if args.action=='status':
        result=run('is-active',NAME);print(result.stdout.strip() or 'unknown');return
    if args.action=='uninstall':
        if not unit.exists():print('没有本项目用户服务。');return
        run('disable','--now',NAME,check=True);unit.unlink();run('daemon-reload',check=True);print('已移除本项目 systemd 用户服务。');return
    # Refuse a second supervisor; it must be stopped through the documented owner command.
    receipt=ROOT/'var/supervisor.json'
    if receipt.exists() and run('is-active','--quiet',NAME).returncode:
        try:
            record=json.loads(receipt.read_text());stamp=subprocess.run(['ps','-p',str(record['pid']),'-o','lstart='],capture_output=True,text=True,timeout=5).stdout.strip()
            if record.get('stamp') and stamp==record['stamp']:raise SystemExit('请先停止当前会话监管：python3 scripts/stay_online.py stop')
        except (ValueError,KeyError):pass
    if unit.exists() and unit.read_text()!=body and run('is-active','--quiet',NAME).returncode==0:raise SystemExit('服务定义有变化；先明确停止本项目用户服务，再重新安装。')
    previous=unit.read_text() if unit.exists() else None
    unit.parent.mkdir(parents=True,exist_ok=True);unit.write_text(body);unit.chmod(0o600)
    try:
        run('daemon-reload',check=True)
        (ROOT/'var/services.paused').unlink(missing_ok=True)
        run('enable','--now',NAME,check=True)
        run('is-active','--quiet',NAME,check=True)
    except (OSError,subprocess.SubprocessError):
        if previous is None:run('disable','--now',NAME);unit.unlink(missing_ok=True)
        else:unit.write_text(previous)
        run('daemon-reload')
        raise SystemExit('用户服务未能启动；已尝试恢复原定义。请检查 systemd 用户会话和本机日志。') from None
    print('systemd 已报告用户服务 active；请继续检查渠道健康和真实微信往返。退出登录/重启后是否运行取决于目标机用户管理器与 linger 设置，本工具没有修改它们。')

if __name__=='__main__':main()
