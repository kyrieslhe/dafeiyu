"""Actual experience timeline and opt-in bounded interest exploration."""
import json
from datetime import datetime
from zoneinfo import ZoneInfo


def initialize(fish):
    fish.db.executescript('''
    CREATE TABLE IF NOT EXISTS episodes (id INTEGER PRIMARY KEY,source TEXT UNIQUE,kind TEXT,content TEXT,created REAL);
    CREATE TABLE IF NOT EXISTS reflections (id INTEGER PRIMARY KEY,content TEXT,sources TEXT,state TEXT DEFAULT 'pending',created REAL);
    CREATE TABLE IF NOT EXISTS interests (id INTEGER PRIMARY KEY,topic TEXT UNIQUE,created REAL);
    CREATE TABLE IF NOT EXISTS life_plan (singleton INTEGER PRIMARY KEY CHECK(singleton=1),enabled INTEGER DEFAULT 0,at TEXT DEFAULT '10:00',last_day TEXT,next_index INTEGER DEFAULT 0);
    INSERT OR IGNORE INTO life_plan(singleton) VALUES (1);
    ''')
    with fish.db:
        fish.db.execute('DELETE FROM episodes WHERE created<?',(fish.clock()-90*86400,))


def record(fish,source,kind,content):
    with fish.db:
        fish.db.execute('INSERT OR IGNORE INTO episodes(source,kind,content,created) VALUES (?,?,?,?)',(source,kind,content[:2000],fish.clock()))


def due(fish,now):
    local=datetime.fromtimestamp(now,ZoneInfo('Asia/Hong_Kong'))
    day,at=local.strftime('%Y-%m-%d'),local.strftime('%H:%M')
    with fish.db:
        fish.db.execute('UPDATE life_plan SET enabled=enabled WHERE singleton=1')  # acquire writer before admission
        if fish.db.execute("SELECT value FROM settings WHERE key='paused'").fetchone()[0]=='1':return
        plan=fish.db.execute('SELECT * FROM life_plan WHERE singleton=1').fetchone()
        if not plan['enabled'] or plan['last_day']==day or at<plan['at']:return
        topics=fish.rows('SELECT topic FROM interests ORDER BY id')
        if not topics:return
        if fish.db.execute('SELECT count(*) FROM tasks WHERE created>?',(now-86400,)).fetchone()[0]>=10:return
        topic=topics[plan['next_index']%len(topics)]['topic']
        fish.db.execute("INSERT OR IGNORE INTO tasks(id,kind,goal,state,due,created) VALUES (?,'explore',?,'queued',?,?)",('life-'+day,'围绕兴趣「'+topic+'」找一个值得了解的问题，研究后用简洁中文分享，有来源、个人判断与不确定性。不要编造活动。',now,now))
        fish.db.execute('UPDATE life_plan SET last_day=?,next_index=next_index+1 WHERE singleton=1',(day,))


def command(fish,name,argument):
    if name=='/recall':
        from .memory import recall
        return recall(fish,argument)
    if name=='/pin':
        with fish.db:
            changed=fish.db.execute('UPDATE memory_meta SET importance=5 WHERE memory_id=?',(int(argument),)).rowcount
        return '已设为常驻记忆。' if changed else '没有这个记忆编号。'
    if name=='/unpin':
        with fish.db:fish.db.execute('UPDATE memory_meta SET importance=1 WHERE memory_id=?',(int(argument),))
        return '已取消常驻。'
    if name=='/timeline':
        return fish.rows('SELECT * FROM episodes ORDER BY id DESC LIMIT 20')
    if name=='/reflect':
        return '整理任务已入队：'+fish.enqueue('reflect','根据真实记录整理一个可能值得保留的经验；不要把推断当事实。')
    if name=='/reflections':return fish.rows("SELECT * FROM reflections WHERE state='pending' ORDER BY id DESC LIMIT 20")
    if name in ('/accept','/dismiss'):
        from .memory import remember
        row=fish.db.execute("SELECT * FROM reflections WHERE id=? AND state='pending'",(int(argument),)).fetchone()
        if not row:return '没有这个待确认的经验。'
        if name=='/accept':remember(fish,row['content'],kind='experience',source='reflection:'+str(row['id']))
        with fish.db:fish.db.execute('UPDATE reflections SET state=? WHERE id=?',('accepted' if name=='/accept' else 'dismissed',row['id']))
        return '已确认并记住这条经验。' if name=='/accept' else '已忽略，不再反复建议。'
    if name=='/interest':
        if argument:
            if len(argument)>120:raise ValueError('兴趣主题最多 120 字符。')
            from .memory import reject_secret
            reject_secret(argument)
            with fish.db:
                if fish.db.execute('SELECT count(*) FROM interests').fetchone()[0]>=10:raise ValueError('最多十个兴趣主题。')
                fish.db.execute('INSERT OR IGNORE INTO interests(topic,created) VALUES (?,?)',(argument,fish.clock()))
        return fish.rows('SELECT * FROM interests ORDER BY id')
    if name=='/uninterest':
        with fish.db:fish.db.execute('DELETE FROM interests WHERE id=?',(int(argument),))
        return '已移除兴趣。'
    if name=='/life':
        if argument=='off':
            with fish.db:fish.db.execute('UPDATE life_plan SET enabled=0 WHERE singleton=1')
            return '自主探索已关闭；已入队任务可单独取消。'
        if argument.startswith('on '):
            at=argument[3:].strip();datetime.strptime(at,'%H:%M')
            if len(at)!=5:raise ValueError('格式：/life on 10:00（香港时间）')
            if not fish.db.execute('SELECT count(*) FROM interests').fetchone()[0]:raise ValueError('先用 /interest 主题 添加兴趣。')
            with fish.db:fish.db.execute('UPDATE life_plan SET enabled=1,at=? WHERE singleton=1',(at,))
            return '已授权每天香港时间 '+at+' 最多一次兴趣研究，消耗 Codex 额度。离线后只补当天一次，遵守暂停与安静时间。'
        return {'plan':fish.rows('SELECT * FROM life_plan'),'interests':fish.rows('SELECT * FROM interests'),'timezone':'Asia/Hong_Kong','default':'off','daily_limit':1}
    if name=='/explore':
        topic=argument or (fish.rows('SELECT topic FROM interests ORDER BY id LIMIT 1') or [{'topic':''}])[0]['topic']
        if not topic:raise ValueError('请提供探索主题或先添加兴趣。')
        return '探索任务已入队：'+fish.enqueue('explore',topic)
    return None


COMMANDS={'/recall','/pin','/unpin','/timeline','/reflect','/reflections','/accept','/dismiss','/interest','/uninterest','/life','/explore'}
