"""Bounded anonymous Bilibili, NASA and NOAA short clips. No cookies, signed-account APIs or external parsers."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import uuid
from urllib.parse import urlencode,urljoin,urlsplit
from .core import ModelError

MAX_BYTES=20*1024*1024


def cdn_url(url,source='bilibili'):
    p=urlsplit(url)
    allowed=(source=='bilibili' and p.hostname and p.hostname.endswith('.bilivideo.com')) or (source=='noaa' and ((p.hostname=='oceantoday.noaa.gov' and re.fullmatch('/[a-z0-9_-]+/[A-Za-z0-9_.-]+[.]mp4',p.path)) or (p.hostname=='cdn.oceanservice.noaa.gov' and re.fullmatch('/oceantodayprod/media/[a-z0-9_-]+/[A-Za-z0-9_.-]+[.]mp4',p.path)))) or (source=='nasa' and p.hostname=='images-assets.nasa.gov' and p.path.startswith('/video/') and p.path.endswith('.mp4'))
    if p.scheme!='https' or not allowed or p.username or p.password or p.port not in (None,443):raise ModelError('播放资源不属于允许的公开 HTTPS CDN。')
    return url


def resolve(page):
    from .platforms import canonical
    from .research import fetch
    page=canonical('bilibili',page);bvid=page.rsplit('/',1)[-1]
    result=json.loads(fetch('https://api.bilibili.com/x/web-interface/view?'+urlencode({'bvid':bvid}))['text'])
    if not isinstance(result,dict):raise ModelError('公开条目元数据格式无效。')
    data=result.get('data',{})
    if result.get('code')!=0 or not isinstance(data,dict):raise ModelError('公开条目元数据不可用。')
    duration=data.get('duration');pages=data.get('pages',[])
    if data.get('rights',{}).get('pay') or data.get('is_upower_exclusive') or not isinstance(pages,list) or len(pages)!=1:raise ModelError('仅分析可匿名获取的单段公开短片。')
    if type(duration) not in (int,float) or not 0<duration<=120 or type(data.get('cid')) is not int:raise ModelError('公开视频超过两分钟或没有可核验时长。')
    playback=json.loads(fetch('https://api.bilibili.com/x/player/playurl?'+urlencode({'bvid':bvid,'cid':data['cid'],'qn':16,'fnval':1}))['text'])
    if not isinstance(playback,dict):raise ModelError('公开播放元数据格式无效。')
    stream=playback.get('data',{})
    if playback.get('code')!=0 or not isinstance(stream,dict) or stream.get('is_preview') or stream.get('format')!='mp4':raise ModelError('没有可匿名分析的普通 MP4 资源。')
    files=stream.get('durl',[])
    if not isinstance(files,list) or len(files)!=1:raise ModelError('仅支持一个受限 MP4 文件。')
    item=files[0]
    if not isinstance(item,dict):raise ModelError('播放资源格式无效。')
    size=item.get('size');length=item.get('length');millis=stream.get('timelength')
    if type(size) is not int or not 0<size<=MAX_BYTES or type(length) not in (int,float) or not 0<length<=120000 or type(millis) not in (int,float) or not 0<millis<=120000:raise ModelError('公开视频超过两分钟或20MB限制。')
    media=None
    backups=item.get('backup_url',[])
    for candidate in [item.get('url','')]+(backups if isinstance(backups,list) else []):
        try:media=cdn_url(candidate);break
        except (ModelError,ValueError,TypeError):continue
    if not media:raise ModelError('没有允许的公开 HTTPS CDN。')
    return {'page':page,'title':str(data.get('title',''))[:300],'description':str(data.get('desc',''))[:1500], 'duration':duration,'size':size,'media_url':media}


def _download(url,home,name,expected,page,source='bilibili'):
    from .research import target,PinnedHTTPS
    from .platforms import canonical
    if source=='noaa':
        from .noaa_video import canonical as noaa_page
        page=noaa_page(page)
    elif source=='nasa':
        from .nasa_video import canonical as nasa_page
        page=nasa_page(page)
    else:page=canonical('bilibili',page)
    if source in ('nasa','noaa') and expected is None:bounded_only=True
    else:bounded_only=False
    if not re.fullmatch('[0-9a-f]{32}[.]mp4',name) or (not bounded_only and (type(expected) is not int or not 0<expected<=MAX_BYTES)):raise ModelError('下载参数无效。')
    root=Path(home).resolve()/'media/video-inputs';root.mkdir(parents=True,exist_ok=True,mode=0o700)
    if root.resolve()!=root:raise ModelError('媒体目录无效。')
    path=root/name
    if path.exists() or path.is_symlink():raise ModelError('不覆盖已有媒体。')
    try:
        for _ in range(3):
            parsed,address=target(cdn_url(url,source));connection=PinnedHTTPS(parsed.hostname,address)
            try:
                request=parsed.path or '/'
                if parsed.query:request+='?'+parsed.query
                connection.request('GET',request,headers={'User-Agent':'Dafeiyu public video reader','Referer':page,'Accept-Encoding':'identity'})
                response=connection.getresponse()
                if response.status in (301,302,303,307,308):url=urljoin(url,response.getheader('Location',''));continue
                if response.status!=200:raise ModelError('播放资源拒绝匿名读取。')
                if response.getheader('Content-Encoding','identity').lower() not in ('','identity'):raise ModelError('播放资源编码不支持。')
                declared=response.getheader('Content-Length')
                if bounded_only:
                    if not declared or not declared.isdigit() or not 0<int(declared)<=MAX_BYTES:raise ModelError('官方短片缺少受限大小信息或超过20MB。')
                    expected=int(declared);bounded_only=False
                if declared and int(declared)!=expected:raise ModelError('播放资源大小与公开元数据不一致。')
                import os
                fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600);total=0;digest=hashlib.sha256()
                with os.fdopen(fd,'wb') as output:
                    while True:
                        block=response.read(min(65536,expected-total+1))
                        if not block:break
                        total+=len(block)
                        if total>expected:raise ModelError('播放资源超过下载上限。')
                        output.write(block);digest.update(block)
                if total!=expected:raise ModelError('播放资源下载不完整。')
                with path.open('rb') as source:header=source.read(12)
                if header[4:8]!=b'ftyp':raise ModelError('播放资源不是受支持的 MP4。')
                return {'bytes':total,'sha256':digest.hexdigest()}
            finally:connection.close()
        raise ModelError('播放资源重定向超限。')
    except BaseException:
        path.unlink(missing_ok=True);raise


def download(info,home,cancelled=lambda:False):
    import os,signal,time
    if cancelled():raise ModelError('公开视频下载已取消。')
    name=uuid.uuid4().hex+'.mp4';path=Path(home).resolve()/'media/video-inputs'/name
    command=[sys.executable,'-m','dafeiyu.public_video']
    process=None;ok=False
    try:
        process=subprocess.Popen(command,cwd=Path(__file__).resolve().parent.parent,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,start_new_session=True)
        payload=json.dumps({'url':info['media_url'],'home':str(Path(home).resolve()),'name':name,'expected':info['size'],'page':info['page'],'source':info.get('source','bilibili')})
        start=time.monotonic()
        try:stdout,_=process.communicate(payload,timeout=.25)
        except subprocess.TimeoutExpired:
            while True:
                if cancelled() or time.monotonic()-start>30:raise ModelError('公开视频下载已取消或超过30秒。')
                try:stdout,_=process.communicate(timeout=.25);break
                except subprocess.TimeoutExpired:continue
        result=json.loads(stdout)
        if process.returncode or type(result.get('bytes')) is not int or not 0<result['bytes']<=MAX_BYTES or (info['size'] is not None and result['bytes']!=info['size']) or not re.fullmatch('[0-9a-f]{64}',result.get('sha256','')):raise ModelError('未能完成受限公开视频下载。')
        ok=True;return path,result
    except (OSError,ValueError):raise ModelError('公开短片下载失败。') from None
    finally:
        if process and process.poll() is None:
            try:os.killpg(process.pid,signal.SIGTERM);process.wait(timeout=2)
            except ProcessLookupError:pass
            except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=2)
        if not ok:path.unlink(missing_ok=True)


if __name__=='__main__':
    try:
        value=json.loads(sys.stdin.read(12000))
        print(json.dumps(_download(value['url'],value['home'],value['name'],value['expected'],value['page'],value.get('source','bilibili'))))
    except Exception:print(json.dumps({'error':'公开短片不可用或超过限制。'}));raise SystemExit(1)
