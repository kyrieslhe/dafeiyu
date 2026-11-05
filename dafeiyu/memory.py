"""CJK-aware local recall, explicit facts and durable deletion markers. No model calls."""
import hashlib
import json
import re
import unicodedata

STOP={'什么','怎么','一下','我们','你们','这个','那个','可以','帮我','记得','记住','知道','是不是','有没有'}


def normalize(text):return unicodedata.normalize('NFKC',text).strip().casefold()


def fingerprint(text):return hashlib.sha256(normalize(text).encode()).hexdigest()


def tokens(text):
    value=normalize(text);result=re.findall(r'[a-z0-9][a-z0-9_-]+',value)
    for run in re.findall(r'[\u3400-\u9fff]+',value):
        result.extend(run[i:i+2] for i in range(len(run)-1))
        if len(run)==1:result.append(run)
    return list(dict.fromkeys(t for t in result if t not in STOP))[:256]


def initialize(fish):
    fish.db.create_function('fish_tokens',1,lambda content:' '.join(tokens(content)),deterministic=True)
    fish.db.executescript('''
    CREATE TABLE IF NOT EXISTS memory_meta (memory_id INTEGER PRIMARY KEY,kind TEXT DEFAULT 'fact',confirmed INTEGER DEFAULT 1,importance INTEGER DEFAULT 1,expires REAL,source TEXT DEFAULT 'manual');
    CREATE TABLE IF NOT EXISTS memory_tombstones (normalized TEXT PRIMARY KEY,deleted REAL);
    CREATE TABLE IF NOT EXISTS recall_log (id INTEGER PRIMARY KEY,created REAL,query_hash TEXT,memory_ids TEXT);
    CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(tokens);
    CREATE TRIGGER IF NOT EXISTS fish_memory_insert AFTER INSERT ON memories BEGIN
      INSERT INTO memory_fts(rowid,tokens) VALUES (new.id,fish_tokens(new.content));
      INSERT OR IGNORE INTO memory_meta(memory_id) VALUES (new.id);
    END;
    CREATE TRIGGER IF NOT EXISTS fish_memory_delete AFTER DELETE ON memories BEGIN
      DELETE FROM memory_fts WHERE rowid=old.id;
      DELETE FROM memory_meta WHERE memory_id=old.id;
    END;
    CREATE TRIGGER IF NOT EXISTS fish_memory_update AFTER UPDATE OF content ON memories BEGIN
      DELETE FROM memory_fts WHERE rowid=old.id;
      INSERT INTO memory_fts(rowid,tokens) VALUES(new.id,fish_tokens(new.content));
    END;
    INSERT OR IGNORE INTO memory_meta(memory_id) SELECT id FROM memories;
    INSERT INTO memory_fts(rowid,tokens) SELECT id,fish_tokens(content) FROM memories WHERE id NOT IN (SELECT rowid FROM memory_fts);
    ''')
    with fish.db:
        fish.db.execute('DELETE FROM recall_log WHERE created<?',(fish.clock()-30*86400,))


def recall(fish,query,limit=10,budget=8000):
    terms=tokens(query)[:32];now=fish.clock();selected=[];ids=set();used=0
    def add(rows,reason):
        nonlocal used
        for row in rows:
            item=dict(row)
            if item['id'] in ids or len(selected)>=limit:continue
            item['reason']=reason
            cost=len(json.dumps(item,ensure_ascii=False).encode())
            if used+cost>budget:continue
            used+=cost;ids.add(item['id']);selected.append(item)
    base='SELECT m.id,m.content,m.created,x.kind,x.source FROM memories m JOIN memory_meta x ON x.memory_id=m.id WHERE x.confirmed=1 AND (x.expires IS NULL OR x.expires>?) '
    add(fish.db.execute(base+'AND x.importance>=5 ORDER BY m.created DESC LIMIT 3',(now,)),'pinned')
    if terms:
        expression=' OR '.join('"'+term.replace('"','""')+'"' for term in terms)
        rows=fish.db.execute('''SELECT m.id,m.content,m.created,x.kind,x.source FROM memory_fts
          JOIN memories m ON m.id=memory_fts.rowid JOIN memory_meta x ON x.memory_id=m.id
          WHERE memory_fts MATCH ? AND x.confirmed=1 AND (x.expires IS NULL OR x.expires>?)
          ORDER BY bm25(memory_fts),m.created DESC LIMIT 7''',(expression,now))
        add(rows,'topic_match')
    add(fish.db.execute(base+'ORDER BY m.created DESC LIMIT 2',(now,)),'recent')
    with fish.db:
        fish.db.execute('INSERT INTO recall_log(created,query_hash,memory_ids) VALUES (?,?,?)',
                        (now,hashlib.sha256(query.encode()).hexdigest(),json.dumps([x['id'] for x in selected])))
        fish.db.execute('DELETE FROM recall_log WHERE id NOT IN (SELECT id FROM recall_log ORDER BY id DESC LIMIT 1000)')
    return selected


def reject_secret(text):
    if re.search(r'AGE-SECRET-KEY-[A-Z0-9]{30,}|gh[pousr]_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9_-]{24,}|-----BEGIN .*PRIVATE KEY|(?:密码|口令|验证码|api.?key|access.?token)\s*(?:是|为|[:：=])\s*\S+',text,re.I):
        raise ValueError('这看起来包含密码、验证码或密钥，不写入长期记忆。请保存在密码管理器。')


def remember(fish,text,kind='fact',source='manual'):
    text=text.strip();reject_secret(text)
    if not text or len(text)>2000:raise ValueError('记忆须为 1–2000 字符。')
    with fish.db:
        fish.db.execute('DELETE FROM memory_tombstones WHERE normalized=?',(fingerprint(text),))
        fish.db.execute('INSERT OR IGNORE INTO memories(content,created) VALUES (?,?)',(text,fish.clock()))
        identifier=fish.db.execute('SELECT id FROM memories WHERE content=?',(text,)).fetchone()[0]
        fish.db.execute('UPDATE memory_meta SET kind=?,source=? WHERE memory_id=?',(kind,source,identifier))
    return identifier
