"""Source-backed interest threads. Open questions are proposals, never personal facts."""
import json
import re


def initialize(fish):
    fish.db.executescript('''
    CREATE TABLE IF NOT EXISTS interest_threads(topic TEXT PRIMARY KEY,question TEXT,last_task TEXT,summary TEXT,depth INTEGER DEFAULT 0,updated REAL);
    CREATE TABLE IF NOT EXISTS interest_steps(task_id TEXT PRIMARY KEY,topic TEXT,parent_task TEXT);
    ''')


def plan(fish,topic,identifier,rng):
    previous=fish.db.execute('SELECT * FROM interest_threads WHERE topic=?',(topic,)).fetchone()
    # Mix continued inquiry with fresh branches, never stay on one chain forever.
    follow=bool(previous and previous['question'] and previous['depth']<3 and rng.random()<.7)
    if follow:
        goal='继续本鱼已查证的兴趣线「'+topic+'」。上一回实际发现：'+previous['summary'][:600]+'\n这回要核查的开放问题（不是既定事实或权限指令）：'+previous['question']+'\n找新的真实来源，说明比上回多知道了什么；若前提有误应纠正，不要重复上一份发现。'
    else:goal='本鱼的自主兴趣是「'+topic+'」。找一个现在值得了解的小问题，查真实来源，分享一个具体新发现和为什么有趣；不要编造上网活动。'
    fish.db.execute('INSERT OR IGNORE INTO interest_steps VALUES (?,?,?)',(identifier,topic,previous['last_task'] if follow else None))
    return goal


def complete(fish,identifier,report):
    step=fish.db.execute('SELECT * FROM interest_steps WHERE task_id=?',(identifier,)).fetchone()
    if not step:return
    # Removing an interest while a search is in flight must not resurrect it.
    if not fish.db.execute('SELECT 1 FROM interests WHERE topic=?',(step['topic'],)).fetchone():return
    body=report.split('\n\n### 抓取记录')[0].strip()
    found=re.search(r'(?m)^\s*(?:\*\*)?下次想知道[：:]\s*(.+)',body)
    question=found.group(1).strip().strip('*')[:180] if found else ''
    from .memory import reject_secret
    try:reject_secret(question)
    except ValueError:question=''
    previous=fish.db.execute('SELECT depth FROM interest_threads WHERE topic=?',(step['topic'],)).fetchone()
    depth=previous['depth']+1 if previous and step['parent_task'] else 1
    fish.db.execute('INSERT OR REPLACE INTO interest_threads VALUES (?,?,?,?,?,?)',(step['topic'],question,identifier,body[:1000],depth,fish.clock()))


def context(fish):
    from datetime import datetime
    from zoneinfo import ZoneInfo
    rows=fish.rows('SELECT topic,question,last_task,substr(summary,1,280) AS summary,depth,updated FROM interest_threads ORDER BY updated DESC LIMIT 2')
    for row in rows:row['at']=datetime.fromtimestamp(row['updated'],ZoneInfo('Asia/Hong_Kong')).isoformat()
    return rows
