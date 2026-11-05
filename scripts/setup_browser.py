#!/usr/bin/env python3
"""Install the pinned public-page renderer without accessing browser login profiles."""
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT=Path(__file__).resolve().parent.parent


def install(runtime=None,node_binary=None):
    runtime=Path(runtime or ROOT/'var/browser-runtime').resolve();runtime.mkdir(mode=0o755,parents=True,exist_ok=True);runtime.chmod(0o755)
    for name in ('package.json','package-lock.json','renderer.mjs','seccomp_profile.json','runtime.json','NOTICE','LICENSE.playwright'):
        shutil.copyfile(ROOT/'integrations/browser'/name,runtime/name)
    node=Path(node_binary or ROOT/'var/runtime/node/bin/node');npm=node.parent.parent/'lib/node_modules/npm/bin/npm-cli.js'
    if not node.exists():
        node=Path(shutil.which('node') or '')
        if not node.is_file():raise SystemExit('先安装 Node 26 运行时。')
        command=['npm']
    else:command=[str(node),str(npm)]
    subprocess.run(command+['ci','--ignore-scripts','--no-fund','--prefix',str(runtime)],check=True)
    image=json.loads((runtime/'runtime.json').read_text())['image']
    subprocess.run(['docker','pull',image],check=True)
    print('公开网页隔离浏览器已安装。不会导入个人浏览器账号或凭据。')
    return runtime

if __name__=='__main__':install()
