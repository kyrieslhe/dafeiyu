"""Public HTTPS resource broker for a browser with Docker networking disabled."""
import base64
import hashlib
import json
import sys
from urllib.parse import urljoin
from .research import target,PinnedHTTPS,ResearchError


def fetch(url):
    parsed,address=target(url)
    connection=PinnedHTTPS(parsed.hostname,address)
    try:
        path=parsed.path or '/'
        if parsed.query:path+='?'+parsed.query
        connection.request('GET',path,headers={'User-Agent':'Dafeiyu-public-browser/0.1','Accept-Encoding':'identity'})
        response=connection.getresponse()
        mime=response.getheader('Content-Type','application/octet-stream')
        if response.status in (301,302,303,307,308):
            location=urljoin(url,response.getheader('Location',''))
            if not location.startswith('https://'):raise ResearchError('拒绝浏览器降级重定向。')
            return {'status':response.status,'headers':{'location':location},'body':'','size':0,'sha256':hashlib.sha256(b'').hexdigest()}
        if response.getheader('Content-Encoding','identity').lower() not in ('identity',''):raise ResearchError('暂不处理强制压缩资源。')
        if mime.lower().startswith(('video/','audio/')):raise ResearchError('浏览器阶段不下载音视频流。')
        data=response.read(1000001)
        if len(data)>1000000:raise ResearchError('浏览器单项资源超过 1MB。')
        return {'status':response.status,'headers':{'content-type':mime},'body':base64.b64encode(data).decode(),'size':len(data),'sha256':hashlib.sha256(data).hexdigest()}
    finally:connection.close()


if __name__=='__main__':
    try:
        raw=sys.stdin.read(8193)
        if len(raw)>8192:raise ResearchError('URL 超长。')
        value=fetch(json.loads(raw)['url']);print(json.dumps({'ok':True,**value}))
    except Exception as error:
        print(json.dumps({'ok':False,'error':str(error) if isinstance(error,ResearchError) else '公开资源抓取失败。'},ensure_ascii=False))
