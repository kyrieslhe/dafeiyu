"""Durable text bursts and paced replies, separate from the serial gateway and research worker."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import time
from .core import Fish,ModelError


def initialize(fish):
    fish.db.execute('''CREATE TABLE IF NOT EXISTS conversation_inbox (
      id INTEGER PRIMARY KEY,inbound_id TEXT UNIQUE,account TEXT,sender TEXT,content TEXT,
      state TEXT,created REAL,claimed REAL,reply TEXT)''')
    fish.db.commit()


def enqueue(fish,key,account,sender,text):
    initialize(fish)
    with fish.db:
        fish.db.execute("INSERT OR IGNORE INTO conversation_inbox(inbound_id,account,sender,content,state,created) VALUES (?,?,?,?,'queued',?)",(key,account,sender,text,fish.clock()))
        fish.db.execute("UPDATE inbound SET state='buffered' WHERE id=?",(key,))
    return ''


def bubbles(text):
    # Paragraphs express semantic boundaries; preserve code, lists and long explanations.
    if len(text)>900 or '```' in text or re.search(r'(?m)^\s*(?:[-*]|\d+[.)]) ',text):return [text]
    parts=[p.strip() for p in text.split('\n\n') if p.strip()]
    if 1<len(parts)<=3:return parts
    return [text]


def step(fish,runner=subprocess.run,sleep=time.sleep):
    initialize(fish);now=fish.clock()
    with fish.db:
        fish.db.execute("UPDATE conversation_inbox SET state='unknown' WHERE state IN ('working','sending') AND claimed<?",(now-180,))
        fish.db.execute("UPDATE inbound_stats SET finished=?,outcome='interrupted' WHERE finished IS NULL AND id IN (SELECT inbound_id FROM conversation_inbox WHERE state='unknown')",(now,))
        fish.db.execute("DELETE FROM conversation_inbox WHERE created<?",(now-30*86400,))
        binding=fish.db.execute('SELECT * FROM channel_binding WHERE singleton=1').fetchone()
        if not binding:return
        rows=fish.rows("SELECT * FROM conversation_inbox WHERE state='queued' ORDER BY id LIMIT 12")
        if not rows:return
        # Wait for a quiet gap, but bound waiting when someone sends continuously.
        if now-rows[-1]['created']<1.8 and now-rows[0]['created']<8:return
        rows=[r for r in rows if r['account']==binding['account'] and r['sender']==binding['sender']]
        if not rows:return
        chosen=[];size=0
        for row in rows:
            if chosen and (chosen[0]['content'].startswith('/') or row['content'].startswith('/')):break
            if chosen and size+len(row['content'])+2>12000:break
            chosen.append(row);size+=len(row['content'])+2
        ids=[r['id'] for r in chosen];marks=','.join('?' for _ in ids)
        changed=fish.db.execute("UPDATE conversation_inbox SET state='working',claimed=? WHERE state='queued' AND id IN ("+marks+')',[now]+ids).rowcount
        if changed!=len(ids):return
    before=fish.db.execute('SELECT coalesce(max(id),0) FROM messages').fetchone()[0]
    before_episode=fish.db.execute('SELECT coalesce(max(id),0) FROM episodes').fetchone()[0]
    try:reply=fish.command('\n'.join(r['content'] for r in chosen))
    except (ValueError,ModelError):reply='鱼脑袋这次没接上，暂时没能生成回复。你可以稍后再试。'
    except Exception:reply='本鱼这次处理失败了，请稍后再试。'
    if not isinstance(reply,str):reply=json.dumps(reply,ensure_ascii=False)
    def current():
        active=fish.db.execute('SELECT * FROM channel_binding WHERE singleton=1').fetchone()
        existing=fish.db.execute("SELECT 1 FROM conversation_inbox WHERE id=? AND state IN ('working','sending')",(ids[0],)).fetchone()
        newer=fish.db.execute("SELECT 1 FROM conversation_inbox WHERE id>? AND state='queued'",(ids[-1],)).fetchone()
        return existing and active and active['account']==binding['account'] and active['sender']==binding['sender'] and not newer
    if not current():
        with fish.db:
            fish.db.execute("UPDATE conversation_inbox SET state='superseded' WHERE id IN ("+marks+')',ids)
            for row in chosen:
                fish.db.execute("UPDATE inbound SET state='completed',reply=NULL WHERE id=?",(row['inbound_id'],))
                fish.db.execute("UPDATE inbound_stats SET finished=?,outcome='superseded' WHERE id=?",(fish.clock(),row['inbound_id']))
            # Keep the user's actual text, but never retain an unsent answer as spoken history.
            fish.db.execute("DELETE FROM messages WHERE id>? AND role='assistant'",(before,))
            fish.db.execute("DELETE FROM episodes WHERE id>? AND kind='conversation'",(before_episode,))
        return 'superseded'
    with fish.db:fish.db.execute("UPDATE conversation_inbox SET state='sending',reply=? WHERE id IN ("+marks+')',[reply]+ids)
    state='accepted';sent=[]
    for index,part in enumerate(bubbles(reply)):
        if index:
            sleep(min(2.5,.6+len(part)/100))
            if not current():state='interrupted';break
        try:
            result=runner([str(Path(__file__).resolve().parent.parent/'scripts/openclaw'),'message','send','--channel','openclaw-weixin','--account',binding['account'],'--target',binding['sender'],'--message',part,'--json'],capture_output=True,text=True,timeout=45)
            if result.returncode:state='delivery_unknown';break
            json.loads(result.stdout);sent.append(part)
        except (OSError,ValueError,subprocess.TimeoutExpired):state='delivery_unknown';break
    with fish.db:
        fish.db.execute('UPDATE conversation_inbox SET state=? WHERE id IN ('+marks+')',[state]+ids)
        if state!='accepted':
            fish.db.execute("UPDATE messages SET content=? WHERE id>? AND role='assistant'",('\n\n'.join(sent) if sent else '（这次回复未确认送出）',before))
            fish.db.execute("DELETE FROM episodes WHERE id>? AND kind='conversation'",(before_episode,))
        for row in chosen:
            fish.db.execute("UPDATE inbound SET state='completed',reply=NULL WHERE id=?",(row['inbound_id'],))
            fish.db.execute("UPDATE inbound_stats SET finished=?,outcome=? WHERE id=?",(fish.clock(),state,row['inbound_id']))
    return state


def main():
    import fcntl
    parser=argparse.ArgumentParser();parser.add_argument('--home',default='var');args=parser.parse_args();fish=Fish(args.home)
    from .channel import tables
    tables(fish)
    lock=(fish.home/'conversation.lock').open('a')
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    try:
        while True:step(fish);time.sleep(.25)
    except KeyboardInterrupt:pass
    finally:fish.close()

if __name__=='__main__':main()
