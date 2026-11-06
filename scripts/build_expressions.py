#!/usr/bin/env python3
"""Derive original vector chat expressions; optional macOS Quick Look PNG export."""
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parent.parent
EXPRESSIONS={'happy':'好耶！','curious':'让本鱼想想','sleepy':'鱼饼摊平','cheer':'一起加油！'}


def build():
    source=(ROOT/'assets/whale.svg').read_text()
    source=source.replace('height="400" viewBox="0 0 640 400"','height="640" viewBox="0 0 640 640"').replace('height="376"','height="616"')
    lines=[]
    for line in source.splitlines():
        if line.startswith('<text') or 'x="398"' in line or 'm421 103' in line:continue
        lines.append(line)
    source='\n'.join(lines).replace('<circle cx="505"','<g transform="translate(0 80)"><circle cx="505"').replace('</svg>','</g></svg>')
    output=ROOT/'assets/expressions';output.mkdir(exist_ok=True)
    for name,label in EXPRESSIONS.items():
        value=source
        if name in ('sleepy','cheer'):
            value=value.replace('<ellipse cx="446" cy="210" rx="9" ry="13" fill="#193956"/><circle cx="449" cy="206" r="3" fill="white"/>','<path d="M434 211q12 -12 24 0" fill="none" stroke="#193956" stroke-width="6" stroke-linecap="round"/>')
        if name=='curious':value=value.replace('rx="9" ry="13"','rx="13" ry="16"')
        value=value.replace('</svg>','<text x="320" y="545" text-anchor="middle" font-family="system-ui,sans-serif" font-size="58" font-weight="700" fill="#28506f">'+label+'</text></svg>')
        path=output/(name+'.svg');path.write_text(value)
        with tempfile.TemporaryDirectory() as temporary:
            subprocess.run(['qlmanage','-t','-s','480','-o',temporary,str(path)],check=True,capture_output=True)
            shutil.copyfile(Path(temporary)/(path.name+'.png'),output/(name+'.png'))

if __name__=='__main__':build()
