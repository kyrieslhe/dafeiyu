#!/usr/bin/env python3
"""Reproducible local npm repack: keep upstream code, unbundle and patch dependencies."""
import base64
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path,PurePosixPath
import tarfile
import urllib.request

ROOT=Path(__file__).resolve().parent.parent
VERSION='12.2.2'
LOCAL_VERSION=VERSION+'+dafeiyu.1'


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--check',action='store_true');args=parser.parse_args()
    prior=ROOT/'integrations/runtime/vendor/provenance.json'
    if prior.exists():
        pinned=json.loads(prior.read_text())['upstream']
        if pinned['url']!='https://registry.npmjs.org/npm/-/npm-'+VERSION+'.tgz':raise SystemExit('Unexpected pinned upstream source')
        metadata={'dist':{'tarball':pinned['url'],'integrity':pinned['integrity']}}
    else:metadata=json.load(urllib.request.urlopen('https://registry.npmjs.org/npm/'+VERSION,timeout=20))
    source=urllib.request.urlopen(metadata['dist']['tarball'],timeout=30).read(20000001)
    algorithm,expected=metadata['dist']['integrity'].split('-',1)
    if algorithm!='sha512' or base64.b64encode(hashlib.sha512(source).digest()).decode()!=expected:raise SystemExit('Upstream npm integrity mismatch')
    files={};modes={};removed=0
    with tarfile.open(fileobj=io.BytesIO(source),mode='r:gz') as archive:
        for member in archive:
            name=PurePosixPath(member.name)
            if not name.parts or name.parts[0]!='package' or '..' in name.parts or name.is_absolute():raise SystemExit('Unsafe upstream archive path')
            if len(name.parts)>1 and name.parts[1]=='node_modules':removed+=member.isfile();continue
            if member.isdir():continue
            if not member.isfile():raise SystemExit('Unexpected upstream archive entry')
            if name.as_posix() in ('package/package-lock.json','package/npm-shrinkwrap.json'):continue
            files[name.as_posix()]=archive.extractfile(member).read();modes[name.as_posix()]=member.mode&0o777
    package=json.loads(files['package/package.json'])
    package['version']=LOCAL_VERSION;package['bundleDependencies']=[];package.pop('bundledDependencies',None)
    package['dependencies']['glob']='14.0.3';package['dependencies']['minimatch']='11.0.4'
    package['description']+=' (Dafeiyu local security repack; unbundled dependencies)'
    files['package/package.json']=(json.dumps(package,ensure_ascii=False,indent=2)+'\n').encode()
    notice=('Dafeiyu local npm security repack '+LOCAL_VERSION+'\nStandard version: '+metadata['dist']['tarball']+'\nUpstream npm code and license preserved. Changes: version/description; remove bundled node_modules and shrinkwrap; glob 14.0.3, minimatch 11.0.4; normal dependencies locked by the companion package-lock. No upstream JavaScript source patches.\nThis modified npm package remains under its upstream Artistic-2.0 license; see LICENSE.\n')
    files['package/DAFEIYU-REPACK-NOTICE.txt']=notice.encode();modes['package/DAFEIYU-REPACK-NOTICE.txt']=0o644
    destination=ROOT/'integrations/runtime/vendor';destination.mkdir(parents=True,exist_ok=True)
    output=destination/'npm-12.2.2-dafeiyu.1.tgz'
    raw=io.BytesIO()
    with gzip.GzipFile(filename='',mode='wb',fileobj=raw,mtime=0) as compressed,tarfile.open(fileobj=compressed,mode='w') as archive:
        for name in sorted(files):
            entry=tarfile.TarInfo(name);entry.size=len(files[name]);entry.mode=modes.get(name,0o644);entry.mtime=0;entry.uid=entry.gid=0
            archive.addfile(entry,io.BytesIO(files[name]))
    built=raw.getvalue()
    if args.check:
        if not output.exists() or output.read_bytes()!=built:raise SystemExit('Repacked artifact differs from pinned reproducible build')
        print('Reproducible npm artifact matches checked-in source patch.');return
    output.write_bytes(built)
    provenance={'upstream':{'package':'npm','version':VERSION,'url':metadata['dist']['tarball'],'integrity':metadata['dist']['integrity']},'local_version':LOCAL_VERSION,'sha256':hashlib.sha256(output.read_bytes()).hexdigest(),'removed_bundled_files':removed,'changes':['unbundle dependency graph','glob=14.0.3','minimatch=11.0.4','local build metadata and notice'],'license':package.get('license')}
    (destination/'provenance.json').write_text(json.dumps(provenance,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'bytes':output.stat().st_size,'local_version':LOCAL_VERSION,'removed_bundled_files':removed,'sha256':provenance['sha256']},indent=2))

if __name__=='__main__':main()
