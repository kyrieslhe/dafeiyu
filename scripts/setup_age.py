#!/usr/bin/env python3
"""Install the pinned, checksum-verified official age binaries locally."""
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import tarfile
import urllib.request

ROOT=Path(__file__).resolve().parent.parent

def main():
    lock=json.loads((ROOT/'integrations/runtime/age.json').read_text())
    arch='arm64' if platform.machine() in ('arm64','aarch64') else 'amd64'
    system=platform.system().lower();key=system+'-'+arch
    if key not in lock['assets']:raise SystemExit('Unsupported age platform')
    name='age-'+lock['version']+'-'+key+'.tar.gz'
    url=lock['source']+'/releases/download/'+lock['version']+'/'+name
    with urllib.request.urlopen(url,timeout=30) as response:data=response.read(20000001)
    if len(data)>20000000 or hashlib.sha256(data).hexdigest()!=lock['assets'][key]:raise SystemExit('age checksum mismatch')
    destination=ROOT/'var/runtime/age';destination.mkdir(parents=True,exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(data)) as archive:
        for binary in ['age','age-keygen']:
            member=archive.getmember('age/'+binary)
            if not member.isfile() or member.size>30000000:raise SystemExit('Invalid age archive member')
            path=destination/binary
            if path.is_symlink():raise SystemExit('Refusing symlink destination')
            path.write_bytes(archive.extractfile(member).read());os.chmod(path,0o755)
    print('Installed checksum-verified age '+lock['version']+' into private runtime directory.')

if __name__=='__main__':main()
