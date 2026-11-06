"""Anonymous official NASA video catalogue, with the existing bounded sampler."""
import json
import re
from urllib.parse import quote,unquote,urlsplit,urlencode
from .core import ModelError


def canonical(url):
    p=urlsplit(url)
    key=unquote(p.path.removeprefix('/details/'))
    if p.scheme!='https' or p.hostname!='images.nasa.gov' or p.username or p.password or p.port not in (None,443) or not p.path.startswith('/details/') or not re.fullmatch('[A-Za-z0-9 _().,-]{1,200}',key):raise ModelError('仅支持 NASA 官方媒体条目。')
    return 'https://images.nasa.gov/details/'+quote(key,safe='')


def keyword(goal,identifier=''):
    if re.search('土星|saturn',goal,re.I):return 'saturn'
    if re.search('月球|moon',goal,re.I):return 'moon'
    if re.search(r'太阳|solar|sun\b',goal,re.I):return 'solar eruption'
    if re.search('宇宙|天文|space|astronomy',goal,re.I):
        return ('Artemis I Mission Trajectory','Earth timelapse','solar eruption')[sum(identifier.encode())%3]
    if re.search('海洋|ocean',goal,re.I):return 'ocean'
    return None


def resolve(item):
    from .research import fetch
    data=item.get('data',[])
    if not data or not isinstance(data[0],dict) or data[0].get('media_type')!='video':raise ModelError('条目不是官方视频。')
    data=data[0];key=data.get('nasa_id','');page=canonical('https://images.nasa.gov/details/'+quote(key,safe=''))
    manifest=json.loads(fetch('https://images-api.nasa.gov/asset/'+quote(key,safe=''))['text'])
    for entry in manifest.get('collection',{}).get('items',[]):
        url=entry.get('href','');p=urlsplit(url)
        # The official catalogue still returns HTTP links: upgrade only this exact host.
        if p.scheme not in ('http','https') or p.hostname!='images-assets.nasa.gov' or p.username or p.password or p.port not in (None,80,443):continue
        path=unquote(p.path)
        if not path.startswith('/video/'+key+'/') or not path.endswith('~small.mp4'):continue
        from .public_video import cdn_url
        media=cdn_url('https://images-assets.nasa.gov'+quote(path,safe='/~'),'nasa')
        return {'page':page,'title':str(data.get('title',''))[:300],'description':str(data.get('description',''))[:1500],'source':'nasa','published_at':str(data.get('date_created',''))[:40],'size':None,'media_url':media}
    raise ModelError('NASA 条目未提供受支持的低清 MP4。')


def read(fish,goal,identifier):
    from .research import fetch
    from .watching import enabled,sampled
    from .sharing import public_goal
    if not enabled(fish):raise ModelError('请先 /watch on 开启短片采样。')
    urls=re.findall(r'https://images[.]nasa[.]gov/details/[^\s<>\])]+',goal)
    if urls:
        page=canonical(urls[0]);key=unquote(urlsplit(page).path[len('/details/'):]);params={'nasa_id':key,'media_type':'video','page_size':1}
    else:
        term=keyword(public_goal(fish,identifier,goal),identifier)
        if not term:raise ModelError('该兴趣暂没有配置官方科学视频目录。')
        params={'q':term,'media_type':'video','page_size':3}
    try:
        items=json.loads(fetch('https://images-api.nasa.gov/search?'+urlencode(params))['text']).get('collection',{}).get('items',[])
        for item in items[:3]:
            if getattr(fish.model,'cancelled',lambda:False)():raise ModelError('官方短片探索已取消。')
            try:
                info=resolve(item)
                if urls and info['page']!=page:continue
                report,metadata=sampled(fish,info['page'],goal,identifier,info=info)
                with fish.db:fish.db.execute('INSERT INTO platform_visits VALUES (NULL,?,?,?,?)',('nasa',info['page'],'sampled_clip',fish.clock()))
                return report,metadata
            except (ModelError,ValueError):continue
    except (ValueError,TypeError,KeyError):pass
    with fish.db:fish.db.execute('INSERT INTO platform_visits VALUES (NULL,?,?,?,?)',('nasa','','sample_unavailable',fish.clock()))
    raise ModelError('没有取得可分析的 NASA 短片，未伪造观看。')
