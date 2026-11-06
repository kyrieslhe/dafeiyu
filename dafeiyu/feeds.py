"""Public RSS/Atom reading, bounded and credential-free. No platform posting."""
import ipaddress
import json
import re
from urllib.parse import urlsplit,parse_qsl
import xml.etree.ElementTree as ET

DEFAULTS=[('海洋 动物 鲸鱼','https://oceanservice.noaa.gov/rss/oceanfacts.xml'),('宇宙 自然 科学','https://www.nasa.gov/news-release/feed/'),('AI 开源 工具','https://github.blog/feed/'),('AI 研究 论文','https://export.arxiv.org/api/query?search_query=cat:cs.AI&sortBy=submittedDate&sortOrder=descending&max_results=5')]


def initialize(fish):
    fish.db.executescript('''
    CREATE TABLE IF NOT EXISTS content_feeds(id INTEGER PRIMARY KEY,topic TEXT,url TEXT UNIQUE);
    CREATE TABLE IF NOT EXISTS feed_reads(url TEXT PRIMARY KEY,task_id TEXT,seen REAL);
    ''')
    with fish.db:
        if fish.db.execute("INSERT OR IGNORE INTO settings VALUES ('feeds_initialized','1')").rowcount:
            fish.db.executemany('INSERT OR IGNORE INTO content_feeds(topic,url) VALUES (?,?)',DEFAULTS)
        fish.db.execute('DELETE FROM feed_reads WHERE seen<?',(fish.clock()-30*86400,))


def validate(url):
    parts=urlsplit(url)
    if any(char.isspace() for char in url):raise ValueError('来源地址不能包含空白。')
    if parts.scheme!='https' or not parts.hostname or parts.username or parts.password or parts.port not in (None,443) or parts.fragment:raise ValueError('来源须为不含登录信息的公开 HTTPS feed URL。')
    if any(re.search('token|password|secret|api.?key|session|authorization|login',key,re.I) for key,value in parse_qsl(parts.query)):raise ValueError('订阅源不能包含认证参数。')
    if parts.hostname.lower()=='localhost':raise ValueError('不允许本机来源。')
    try:address=ipaddress.ip_address(parts.hostname)
    except ValueError:address=None
    if address and not address.is_global:raise ValueError('不允许私网来源。')
    return url


def for_topic(fish,identifier,goal):
    state=fish.db.execute("SELECT value FROM settings WHERE key='feeds_enabled'").fetchone()
    if state and state[0]=='0':return []
    step=fish.db.execute('SELECT topic FROM interest_steps WHERE task_id=?',(identifier,)).fetchone()
    query=step['topic'] if step else goal
    candidates=[row['url'] for row in fish.rows('SELECT topic,url FROM content_feeds ORDER BY id') if any(word.casefold() in query.casefold() for word in row['topic'].split())]
    if not candidates:return []
    return [candidates[sum(identifier.encode())%len(candidates)]]


def entries(text):
    if len(text.encode())>400000 or re.search(r'<!\s*(?:DOCTYPE|ENTITY)',re.sub(r'<!\[CDATA\[.*?\]\]>|<!--.*?-->','',text,flags=re.S),re.I):raise ValueError('订阅源超限或包含实体声明。')
    root=ET.fromstring(text)
    if root.tag.rsplit('}',1)[-1] not in ('rss','feed','RDF'):raise ValueError('不是支持的 RSS/Atom。')
    result=[]
    for node in root.iter():
        if node.tag.rsplit('}',1)[-1] not in ('item','entry'):continue
        title='';url='';summary='';published=''
        for child in node:
            name=child.tag.rsplit('}',1)[-1]
            if name=='title':title=''.join(child.itertext()).strip()[:240]
            elif name=='link' and child.attrib.get('rel','alternate')=='alternate':url=(child.attrib.get('href') or child.text or '').strip()
            elif name in ('pubDate','published','updated'):published=(child.text or '')[:120]
            elif name in ('summary','description'):summary=re.sub('<[^>]+>',' ',''.join(child.itertext()))[:600]
        if url.startswith('http://'):url='https://'+url[7:]
        try:validate(url)
        except ValueError:continue
        if title and url not in [r['url'] for r in result]:result.append({'title':title,'url':url,'summary':summary,**({'published_at':published} if published else {})})
        if len(result)>=12:break
    return result


def command(fish,argument):
    if argument in ('on','off'):
        with fish.db:fish.db.execute("INSERT OR REPLACE INTO settings VALUES ('feeds_enabled',?)",('1' if argument=='on' else '0',))
    elif argument.startswith('add '):
        topic,_,url=argument[4:].partition(' ');url=url.strip();validate(url)
        if not topic or len(topic)>80:raise ValueError('用法：/feeds add 主题 HTTPS订阅源')
        with fish.db:
            if fish.db.execute('SELECT count(*) FROM content_feeds').fetchone()[0]>=10:raise ValueError('最多十个订阅源。')
            fish.db.execute('INSERT OR IGNORE INTO content_feeds(topic,url) VALUES (?,?)',(topic,url))
    elif argument.startswith('remove '):
        with fish.db:fish.db.execute('DELETE FROM content_feeds WHERE id=?',(int(argument[7:]),))
    elif argument:raise ValueError('用法：/feeds、/feeds on|off、/feeds add 主题 HTTPS订阅源、/feeds remove 编号')
    row=fish.db.execute("SELECT value FROM settings WHERE key='feeds_enabled'").fetchone()
    return {'enabled':not row or row[0]=='1','sources':fish.rows('SELECT * FROM content_feeds ORDER BY id'),'scope':'公开内容读取，不登录、不评论、不投稿。'}
