#!/usr/bin/env python3
"""Review tracked Git history without printing matched secret values."""
import re
import subprocess
import sys

PATTERNS=[
 ('GitHub credential',r'gh[pousr]_[A-Za-z0-9]{20,}'),
 ('provider credential',r'sk-(?:proj-)?[A-Za-z0-9_-]{24,}'),
 ('private key',r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
 ('literal token',r'["\x27](?:api_key|access_token|refresh_token|bot_token)["\x27]\s*:\s*["\x27][A-Za-z0-9_.-]{24,}["\x27]'),
 ('private home path',r'/Users/(?!\<|example|your-user)[A-Za-z0-9_.-]+/'),
 ('real WeChat peer',r'o[A-Za-z0-9_-]{24,}@im\.wechat'),
]


def main():
    listed=subprocess.check_output(['git','rev-list','--objects','--all'],text=True)
    failures=[];count=0
    for line in listed.splitlines():
        identifier,_,name=line.partition(' ')
        if not name:continue
        if subprocess.check_output(['git','cat-file','-t',identifier],text=True).strip()!='blob':continue
        count+=1
        if name.startswith('var/') or name.endswith(('.sqlite','.sqlite3','.db','.pem','.p12')) or name in ('.env','auth.json'):
            failures.append((name,'private artifact path'))
        value=subprocess.check_output(['git','cat-file','blob',identifier]).decode(errors='replace')
        for label,pattern in PATTERNS:
            if re.search(pattern,value):failures.append((name,label))
    if failures:
        for name,label in sorted(set(failures)):print('FAIL:',name,'—',label)
        return 1
    print('Privacy audit passed: %s historical blobs checked; no matching private artifacts or credential patterns.'%count)
    print('Heuristic check only; review new integrations and assets separately.')
    return 0

if __name__=='__main__':sys.exit(main())
