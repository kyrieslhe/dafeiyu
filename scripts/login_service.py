#!/usr/bin/env python3
"""Install/remove only Dafeiyu's user LaunchAgent; never a system daemon."""
import argparse
import os
from pathlib import Path
import plistlib
import subprocess
import sys

ROOT=Path(__file__).resolve().parent.parent
LABEL='io.github.kyrieslhe.dafeiyu'


def definition(root=ROOT,python=sys.executable):
    return {'Label':LABEL,'ProgramArguments':[python,str(root/'scripts/supervise.py')],
            'WorkingDirectory':str(root),'RunAtLoad':True,'KeepAlive':True,'ThrottleInterval':30,
            'ProcessType':'Background','Umask':63,
            'EnvironmentVariables':{'PATH':str(root/'var/runtime/node/bin')+':/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin'},
            'StandardOutPath':str(root/'var/service-supervisor.log'),
            'StandardErrorPath':str(root/'var/service-supervisor.log')}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['install','uninstall','status']);args=parser.parse_args()
    if sys.platform!='darwin':raise SystemExit('LaunchAgent 仅支持 macOS。其他平台可手动启动 services.py。')
    plist=Path.home()/'Library/LaunchAgents'/(LABEL+'.plist');domain='gui/'+str(os.getuid())
    if plist.exists():
        existing=plistlib.loads(plist.read_bytes())
        if existing.get('WorkingDirectory')!=str(ROOT):raise SystemExit('同名 LaunchAgent 属于其他目录，未修改。')
    if args.action=='status':
        result=subprocess.run(['launchctl','print',domain+'/'+LABEL],capture_output=True,text=True)
        print('installed and loaded' if result.returncode==0 else 'not loaded');return
    subprocess.run(['launchctl','bootout',domain+'/'+LABEL],capture_output=True)
    subprocess.run([sys.executable,str(ROOT/'scripts/services.py'),'stop','--internal'],check=False)
    if args.action=='uninstall':
        plist.unlink(missing_ok=True);print('已移除大肥鱼登录启动项，并停止本项目服务。');return
    (ROOT/'var/services.paused').unlink(missing_ok=True)
    plist.parent.mkdir(parents=True,exist_ok=True);plist.write_bytes(plistlib.dumps(definition()));os.chmod(plist,0o600)
    result=subprocess.run(['launchctl','bootstrap',domain,str(plist)],capture_output=True,text=True)
    if result.returncode:raise SystemExit('LaunchAgent 加载失败；仍可用 services.py start 手动运行。')
    print('已安装大肥鱼用户登录后台服务；退出登录或休眠期间不保证运行。')

if __name__=='__main__':main()
