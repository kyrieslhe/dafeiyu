"""Daytime jittered curiosity with bounded admissions, grounded sharing and quota holds."""
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
import json
import random
import uuid

TZ=ZoneInfo('Asia/Hong_Kong')


def initialize(fish):
    fish.db.executescript('''
    CREATE TABLE IF NOT EXISTS curiosity_policy (singleton INTEGER PRIMARY KEY CHECK(singleton=1),next_due REAL,last_reason TEXT);
    INSERT OR IGNORE INTO curiosity_policy VALUES (1,NULL,'off');
    CREATE TABLE IF NOT EXISTS curiosity_suppressed (outbox_id INTEGER PRIMARY KEY,reason TEXT,created REAL);
    CREATE TABLE IF NOT EXISTS curiosity_runs (task_id TEXT PRIMARY KEY,day TEXT,started REAL,shared INTEGER DEFAULT 0);
    ''')


def mode(fish):
    row=fish.db.execute("SELECT value FROM settings WHERE key='life_mode'").fetchone()
    return row[0] if row else 'fixed'


def tomorrow(now,rng=random):
    return (datetime.fromtimestamp(now,TZ)+timedelta(days=1)).replace(hour=9,minute=0,second=0,microsecond=0).timestamp()+rng.randint(0,3600)


def next_time(now,delay,rng=random):
    date=datetime.fromtimestamp(now+delay,TZ)
    if date.hour>=22:date=(date+timedelta(days=1)).replace(hour=9,minute=0,second=0,microsecond=0)+timedelta(seconds=rng.randint(0,3600))
    elif date.hour<9:date=date.replace(hour=9,minute=0,second=0,microsecond=0)+timedelta(seconds=rng.randint(0,3600))
    return date.timestamp()


def enable(fish,rng=random):
    if mode(fish)=='random' and fish.db.execute('SELECT enabled FROM life_plan').fetchone()[0]:return '白天随机探索已经开启；原有时间与预算保持不变。用 /life 查看状态。'
    with fish.db:
        if not fish.db.execute('SELECT count(*) FROM interests').fetchone()[0]:
            for topic in ('海洋与动物','宇宙与自然科学','AI 与开源工具','日常生活的有趣知识'):
                fish.db.execute('INSERT INTO interests(topic,created) VALUES (?,?)',(topic,fish.clock()))
        fish.db.execute("INSERT OR REPLACE INTO settings VALUES ('life_mode','random')")
        fish.db.execute('UPDATE life_plan SET enabled=1 WHERE singleton=1')
        fish.db.execute("UPDATE curiosity_policy SET next_due=?,last_reason='scheduled' WHERE singleton=1",(next_time(fish.clock(),rng.randint(600,3600),rng),))
    return '已开启白天随机探索：香港时间 09:00–22:00，通常间隔 2–4 小时，每天最多四次；最多两条新发现进入主动汇报。额度低于 10% 或暂时读不到时暂停新自主任务，恢复后再试，不补跑积压。兴趣由本鱼选择，可用 /interest 调整，/life off 关闭。'


def due(fish,now,rng=random):
    local=datetime.fromtimestamp(now,TZ)
    if not 9<=local.hour<22:return
    with fish.db:
        fish.db.execute('UPDATE curiosity_policy SET next_due=next_due WHERE singleton=1')
        enabled=fish.db.execute('SELECT enabled FROM life_plan').fetchone()[0]
        paused=fish.db.execute("SELECT value FROM settings WHERE key='paused'").fetchone()[0]=='1'
        policy=fish.db.execute('SELECT * FROM curiosity_policy').fetchone()
        if not enabled or paused or policy['next_due'] is None or policy['next_due']>now:return
        if fish.db.execute("SELECT 1 FROM tasks WHERE id LIKE 'curious-%' AND state IN ('queued','running')").fetchone():return
        day=local.strftime('%Y-%m-%d')
        used=fish.db.execute('SELECT count(*) FROM curiosity_runs WHERE day=?',(day,)).fetchone()[0]
        if used>=4:
            fish.db.execute("UPDATE curiosity_policy SET next_due=?,last_reason='daily-budget'",(tomorrow(now,rng),));return
        if fish.db.execute('SELECT count(*) FROM tasks WHERE created>?',(now-86400,)).fetchone()[0]>=10:return
        topics=[r['topic'] for r in fish.rows('SELECT topic FROM interests ORDER BY id')]
        if not topics:return
        recent=fish.rows('SELECT topic,summary,created FROM exploration_notes ORDER BY created DESC LIMIT 3')
        options=[topic for topic in topics if not recent or topic not in recent[0]['topic']] or topics
        from .sharing import choose_topic
        topic=choose_topic(fish,options,rng)
        key='curious-'+uuid.uuid4().hex[:12]
        from .interests import plan
        goal=plan(fish,topic,key,rng)
        fish.db.execute("INSERT INTO tasks(id,kind,goal,state,due,created) VALUES (?,'explore',?,'queued',?,?)",(key,goal[:6000],now,now))
        fish.db.execute("UPDATE curiosity_policy SET next_due=?,last_reason='queued'",(next_time(now,rng.randint(7200,14400),rng),))


def automatic(identifier):return identifier.startswith(('curious-','life-','daily-'))


def may_start(fish,row,now,quota):
    if not automatic(row['id']):return True
    is_random=row['id'].startswith('curious-')
    if is_random:
        enabled=fish.db.execute('SELECT enabled FROM life_plan').fetchone()[0]
        if not enabled or mode(fish)!='random':
            fish.db.execute("UPDATE tasks SET state='cancelled' WHERE id=?",(row['id'],));return False
        local=datetime.fromtimestamp(now,TZ);day=local.strftime('%Y-%m-%d')
        used=fish.db.execute('SELECT count(*) FROM curiosity_runs WHERE day=?',(day,)).fetchone()[0]
        if not 9<=local.hour<22 or used>=4:
            fish.db.execute('UPDATE tasks SET due=? WHERE id=?',(next_time(now,0) if used<4 else tomorrow(now),row['id']));return False
    if quota.get('status')!='ok':
        fish.db.execute('UPDATE tasks SET due=? WHERE id=?',(next_time(now,600) if is_random else now+600,row['id']))
        fish.db.execute('UPDATE curiosity_policy SET last_reason=?',(str(quota.get('status','unknown'))+'-quota',))
        return False
    if is_random:
        fish.db.execute('INSERT OR IGNORE INTO curiosity_runs(task_id,day,started) VALUES (?,?,?)',(row['id'],day,now))
        fish.db.execute("UPDATE curiosity_policy SET last_reason='exploring'")
    return True


def should_share(fish,identifier,summary):
    if not identifier.startswith('curious-'):return True
    from .memory import tokens
    day=datetime.fromtimestamp(fish.clock(),TZ).strftime('%Y-%m-%d')
    if fish.db.execute('SELECT count(*) FROM curiosity_runs WHERE day=? AND shared=1',(day,)).fetchone()[0]>=2:return False
    current=set(tokens(summary))
    for row in fish.rows('SELECT summary FROM exploration_notes WHERE task_id!=? ORDER BY created DESC LIMIT 5',(identifier,)):
        prior=set(tokens(row['summary']));union=current|prior
        if union and len(current&prior)/len(union)>.7:return False
    fish.db.execute("INSERT OR IGNORE INTO curiosity_suppressed SELECT id,'newer-discovery',? FROM outbox WHERE seen=0 AND task_id LIKE 'curious-%' AND task_id!=?",(fish.clock(),identifier))
    fish.db.execute('UPDATE curiosity_runs SET shared=1 WHERE task_id=?',(identifier,))
    return True


def status(fish):
    row=fish.db.execute('SELECT * FROM curiosity_policy').fetchone()
    day=datetime.fromtimestamp(fish.clock(),TZ).strftime('%Y-%m-%d')
    due=row['next_due'];quota=fish.db.execute("SELECT value FROM settings WHERE key='autonomy_quota'").fetchone()
    enabled=bool(fish.db.execute('SELECT enabled FROM life_plan').fetchone()[0])
    running=bool(fish.db.execute("SELECT 1 FROM tasks WHERE id LIKE 'curious-%' AND state='running'").fetchone())
    return {'enabled':enabled,'currently_exploring':running,'mode':mode(fish),'daytime':'09:00–22:00 Asia/Hong_Kong','next_check':datetime.fromtimestamp(due,TZ).isoformat() if due else None,
            'started_today':fish.db.execute('SELECT count(*) FROM curiosity_runs WHERE day=?',(day,)).fetchone()[0],
            'daily_max':4,'share_max':2,'last_reason':row['last_reason'],'quota':json.loads(quota['value']) if quota else None}
