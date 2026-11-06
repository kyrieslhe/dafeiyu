"""Anonymous NOAA Ocean Today clips from its own public directory and download links."""
import random
import re
from urllib.parse import urlsplit
from .core import ModelError

DIRECTORY='https://oceantoday.noaa.gov/marine-life.html'


def canonical(url):
    p=urlsplit(url)
    if p.scheme!='https' or p.hostname!='oceantoday.noaa.gov' or p.username or p.password or p.port not in (None,443) or not re.fullmatch('/[a-z0-9][a-z0-9_-]{0,100}/',p.path):raise ModelError('仅支持 NOAA Ocean Today 官方视频条目。')
    return 'https://oceantoday.noaa.gov'+p.path


def relevant(goal):return bool(re.search('海洋|鲸鱼|动物|海豚|章鱼|ocean|whale|marine',goal,re.I))


def resolve(page):
    from .research import fetch
    from .public_video import cdn_url
    page=canonical(page);source=fetch(page,include_links=True);canonical(source['url'])
    candidates=[]
    for url in source.get('links',[]):
        try:candidates.append(cdn_url(url,'noaa'))
        except (ModelError,ValueError):continue
    candidates.sort(key=lambda url:('_sm' not in url,bool(re.search('_es_|spanish|_spa',url,re.I)),len(url)))
    if not candidates:raise ModelError('官方页面未提供受支持的 MP4 下载。')
    text=source['text'];title=source.get('title') or 'NOAA Ocean Today'
    description='官方科普档案，片段发布时间未核实，不当成近期事件。\n'+text.split('Transcript',1)[-1].split('Transcripción',1)[0][:1500]
    return {'page':page,'title':title,'description':description,'source':'noaa','size':None,'media_url':candidates[0]}


def read(fish,goal,identifier):
    from .research import fetch
    from .watching import enabled,sampled
    if not enabled(fish):raise ModelError('请先 /watch on 开启短片采样。')
    urls=re.findall(r'https://oceantoday[.]noaa[.]gov/[^\s<>\])]+',goal)
    if urls:candidates=[canonical(urls[0])]
    else:
        from .sharing import public_goal
        if not relevant(public_goal(fish,identifier,goal)):raise ModelError('该兴趣暂没有对应海洋视频目录。')
        directory=fetch(DIRECTORY,include_links=True)
        if directory['url']!=DIRECTORY:raise ModelError('官方目录发生跳转，未继续选择视频。')
        candidates=[]
        for url in directory.get('links',[]):
            try:candidates.append(canonical(url))
            except (ModelError,ValueError):continue
        candidates=list(dict.fromkeys(candidates));random.Random(identifier).shuffle(candidates)
    automatic=identifier.startswith(('curious-','life-'))
    if automatic:candidates=[url for url in candidates if not fish.db.execute('SELECT 1 FROM video_choices WHERE url=? AND created>?',(url,fish.clock()-30*86400)).fetchone()]
    if not candidates:raise ModelError('没有新的官方海洋短片候选，未重复推荐。')
    for page in candidates[:3]:
        if not enabled(fish):raise ModelError('短片探索已关闭。')
        if getattr(fish.model,'cancelled',lambda:False)():raise ModelError('海洋短片探索已取消。')
        try:
            info=resolve(page);report,metadata=sampled(fish,page,goal,identifier,info=info)
            if not enabled(fish):raise ModelError('短片探索已关闭。')
            with fish.db:fish.db.execute('INSERT INTO platform_visits VALUES (NULL,?,?,?,?)',('noaa',page,'sampled_clip',fish.clock()))
            return report,metadata
        except (ModelError,ValueError):continue
    if not enabled(fish):raise ModelError('短片探索已关闭。')
    with fish.db:fish.db.execute('INSERT INTO platform_visits VALUES (NULL,?,?,?,?)',('noaa','','sample_unavailable',fish.clock()))
    raise ModelError('没有取得可分析的海洋短片，未伪造观看。')
