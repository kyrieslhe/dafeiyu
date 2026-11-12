"""Durable text bursts and paced replies, separate from the serial gateway and research worker."""
import argparse
import hashlib
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
    with fish.db:
        fish.db.execute("UPDATE settings SET value=value WHERE key='paused'")
        if 'images' not in {row[1] for row in fish.db.execute('PRAGMA table_info(conversation_inbox)')}:fish.db.execute("ALTER TABLE conversation_inbox ADD COLUMN images TEXT DEFAULT '[]'")

        if 'transcribed' not in {row[1] for row in fish.db.execute('PRAGMA table_info(conversation_inbox)')}:fish.db.execute("ALTER TABLE conversation_inbox ADD COLUMN transcribed INTEGER DEFAULT 0")

def enqueue(fish,key,account,sender,text,images=None,transcribed=False):
    initialize(fish)
    with fish.db:
        from .presence import observe
        if not transcribed:observe(fish,text)
        fish.db.execute("INSERT OR IGNORE INTO conversation_inbox(inbound_id,account,sender,content,state,created) VALUES (?,?,?,?,'queued',?)",(key,account,sender,text,fish.clock()))
        if transcribed:fish.db.execute('UPDATE conversation_inbox SET transcribed=1 WHERE inbound_id=?',(key,))
        if images:fish.db.execute('UPDATE conversation_inbox SET images=? WHERE inbound_id=?',(json.dumps(images),key))
        fish.db.execute("UPDATE inbound SET state='buffered' WHERE id=?",(key,))
    return ''


def immediate(text):
    return text in ('/pause','/resume','/life off','/platforms off','/growth off','/watch off','暂停自主任务','继续') or text.startswith(('/cancel ','/quiet '))


def standalone(text):
    from .todos import parse
    from .reminders import parse as reminder_parse
    return text.startswith('/') or parse(text) is not None or reminder_parse(text) is not None


def barrier(fish,key,account,sender):
    initialize(fish)
    with fish.db:fish.db.execute("INSERT OR IGNORE INTO conversation_inbox(inbound_id,account,sender,content,state,created) VALUES (?,?,?,'','control',?)",(key,account,sender,fish.clock()))


def bubbles(text,goal=''):
    # Paragraphs express semantic boundaries; preserve code, lists and long explanations.
    if re.search('正式|别卖萌|不要卖萌|一次发完|不要分条|不要分段',goal):return [text]
    if len(text)>900 or '```' in text or re.search(r'(?m)^\s*(?:[-*]|\d+[.)]) ',text):return [text]
    parts=[p.strip() for p in text.split('\n\n') if p.strip()]
    if 1<len(parts)<=3:return parts
    return [text]


def step(fish,runner=subprocess.run,sleep=time.sleep):
    initialize(fish);now=fish.clock()
    cleanup_images(fish)
    with fish.db:
        fish.db.execute("UPDATE conversation_inbox SET state='unknown' WHERE state IN ('working','sending') AND claimed<?",(now-180,))
        fish.db.execute("UPDATE inbound_stats SET finished=?,outcome='interrupted' WHERE finished IS NULL AND id IN (SELECT inbound_id FROM conversation_inbox WHERE state='unknown')",(now,))
        fish.db.execute("DELETE FROM conversation_inbox WHERE created<?",(now-30*86400,))
        binding=fish.db.execute('SELECT * FROM channel_binding WHERE singleton=1').fetchone()
        if not binding:return
        fish.db.execute("UPDATE conversation_inbox SET state='identity_changed',content='',reply=NULL WHERE state='queued' AND (account!=? OR sender!=?)",(binding['account'],binding['sender']))
        fish.db.execute("UPDATE inbound_stats SET finished=?,outcome='rejected' WHERE finished IS NULL AND id IN (SELECT inbound_id FROM conversation_inbox WHERE state='identity_changed')",(now,))
        rows=fish.rows("SELECT * FROM conversation_inbox WHERE state='queued' ORDER BY id LIMIT 12")
        if not rows:return
        # Wait for a quiet gap, but bound waiting when someone sends continuously.
        recent=fish.db.execute("SELECT count(DISTINCT claimed) FROM conversation_inbox WHERE state='superseded' AND claimed>?",(now-60,)).fetchone()[0]
        gap=min(4,1.8+.6*min(4,recent))
        if now-rows[-1]['created']<gap and now-rows[0]['created']<8:return
        rows=[r for r in rows if r['account']==binding['account'] and r['sender']==binding['sender']]
        if not rows:return
        latest_seen=fish.db.execute('SELECT coalesce(max(id),0) FROM conversation_inbox WHERE account=? AND sender=?',(binding['account'],binding['sender'])).fetchone()[0]
        chosen=[];size=0;image_count=0;image_bytes=0
        for row in rows:
            if chosen and (standalone(chosen[0]['content']) or standalone(row['content'])):break
            if chosen and size+len(row['content'])+2>12000:break
            row_images=json.loads(row['images'] or '[]')
            row_bytes=sum(Path(value).stat().st_size for value in row_images if Path(value).is_file())
            if chosen and (image_count+len(row_images)>2 or image_bytes+row_bytes>12*1024*1024):break
            chosen.append(row);size+=len(row['content'])+2;image_count+=len(row_images);image_bytes+=row_bytes
        ids=[r['id'] for r in chosen];marks=','.join('?' for _ in ids)
        changed=fish.db.execute("UPDATE conversation_inbox SET state='working',claimed=? WHERE state='queued' AND id IN ("+marks+')',[now]+ids).rowcount
        if changed!=len(ids):return
    from .relationship import generation
    started_generation=generation(fish)
    reset_command=chosen[0]['content'].split(' ',1)[0] in ('/clear','/forget','忘记')
    before=fish.db.execute('SELECT coalesce(max(id),0) FROM messages').fetchone()[0]
    before_episode=fish.db.execute('SELECT coalesce(max(id),0) FROM episodes').fetchone()[0]
    def current():
        active=fish.db.execute('SELECT * FROM channel_binding WHERE singleton=1').fetchone()
        existing=fish.db.execute("SELECT 1 FROM conversation_inbox WHERE id=? AND state IN ('working','sending')",(ids[0],)).fetchone()
        newer=fish.db.execute("SELECT 1 FROM conversation_inbox WHERE id>? AND state IN ('queued','control') AND account=? AND sender=?",(latest_seen,binding['account'],binding['sender'])).fetchone()
        if not reset_command and generation(fish)!=started_generation:return False
        return existing and active and active['account']==binding['account'] and active['sender']==binding['sender'] and not newer
    previous_cancel=getattr(fish.model,'cancelled',None)
    if previous_cancel is not None:fish.model.cancelled=lambda:previous_cancel() or not current()
    try:
        text='\n'.join(row['content'] for row in chosen)
        images=[value for row in chosen for value in json.loads(row['images'] or '[]')]
        if not images and not standalone(text) and not re.search('换个话题|不用看图|别看图|算了|不看了',text):
            reset=fish.db.execute("SELECT value FROM settings WHERE key='relationship_reset'").fetchone()
            cutoff=max(now-300,float(reset[0]) if reset else 0)
            prior=fish.db.execute("SELECT images,state,claimed FROM conversation_inbox WHERE id<? AND account=? AND sender=? AND created>? AND images!='[]' AND state IN ('superseded','accepted','interrupted') ORDER BY id DESC LIMIT 1",(ids[0],binding['account'],binding['sender'],cutoff)).fetchone()
            if prior and ((prior['state']=='superseded' and now-prior['claimed']<15) or re.search('图|照片|旁边|那个|这张|那张|左边|右边|颜色|画面|上面|下面',text)):
                rows_with_images=fish.rows("SELECT images FROM conversation_inbox WHERE claimed=? AND account=? AND sender=? AND images!='[]' ORDER BY id",(prior['claimed'],binding['account'],binding['sender']))
                images=[value for row in rows_with_images for value in json.loads(row['images'])][:2]
                with fish.db:fish.db.execute('UPDATE conversation_inbox SET images=? WHERE id=?',(json.dumps(images),ids[0]))
        transcribed=any(row['transcribed'] for row in chosen)
        if images or transcribed:
            if images:
                from .media import stored_image_paths
                images=stored_image_paths(fish.home,images)
            reply=fish.chat(text,images=images or None,allow_actions=not transcribed)
        else:reply=fish.command(text)
    except ValueError as error:reply=str(error)
    except ModelError:reply='鱼脑袋这次没接上，暂时没能生成回复。你可以稍后再试。'
    except Exception:reply='本鱼这次处理失败了，请稍后再试。'
    finally:
        if previous_cancel is not None:fish.model.cancelled=previous_cancel
    if not isinstance(reply,str):reply=json.dumps(reply,ensure_ascii=False)
    if not current():
        with fish.db:
            fish.db.execute("UPDATE conversation_inbox SET state='superseded' WHERE id IN ("+marks+')',ids)
            for row in chosen:
                fish.db.execute("UPDATE inbound SET state='completed',reply=NULL WHERE id=?",(row['inbound_id'],))
                fish.db.execute("UPDATE inbound_stats SET finished=?,outcome='superseded' WHERE id=?",(fish.clock(),row['inbound_id']))
            # Preserve the original user input even when native cancellation prevented chat() from saving it.
            original='\n'.join(row['content'] for row in chosen)
            keep_input=not reset_command and generation(fish)==started_generation and not standalone(original)
            if keep_input and not fish.db.execute("SELECT 1 FROM messages WHERE id>? AND role='user' AND content=?",(before,original)).fetchone():fish.db.execute("INSERT INTO messages(role,content,created) VALUES ('user',?,?)",(original,fish.clock()))
            # Never retain an unsent answer as spoken history.
            fish.db.execute("DELETE FROM messages WHERE id>? AND role='assistant'",(before,))
            fish.db.execute("DELETE FROM episodes WHERE id>? AND kind='conversation'",(before_episode,))
            if keep_input:fish.db.execute("INSERT OR IGNORE INTO episodes(source,kind,content,created) VALUES (?,'conversation',?,?)",('burst-input:'+hashlib.sha256(chosen[0]['inbound_id'].encode()).hexdigest(),'用户原话（此前没有发出回复）：'+original[:1000],fish.clock()))
        return 'superseded'
    with fish.db:fish.db.execute("UPDATE conversation_inbox SET state='sending',reply=? WHERE id IN ("+marks+')',[reply]+ids)
    state='accepted';sent=[]
    for index,part in enumerate(bubbles(reply,'\n'.join(row['content'] for row in chosen))):
        if index:
            sleep(min(2.5,.6+len(part)/100))
            if not current():state='interrupted';break
        try:
            result=runner([str(Path(__file__).resolve().parent.parent/'scripts/openclaw'),'message','send','--channel','openclaw-weixin','--account',binding['account'],'--target',binding['sender'],'--message',part,'--json'],capture_output=True,text=True,timeout=45)
            from .send_outcome import outcome
            if outcome(result)[0]!='accepted':state='delivery_unknown';break
            sent.append(part)
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


def purge_images(fish):
    if not fish.db.execute("SELECT 1 FROM sqlite_master WHERE name='conversation_inbox'").fetchone() or 'images' not in {row[1] for row in fish.db.execute('PRAGMA table_info(conversation_inbox)')}:return
    rows=fish.rows("SELECT images FROM conversation_inbox WHERE state!='queued' AND images!='[]'")
    queued={value for row in fish.rows("SELECT images FROM conversation_inbox WHERE state='queued'") for value in json.loads(row['images'] or '[]')}
    for row in rows:
        for value in json.loads(row['images'] or '[]'):
            path=Path(value);root=fish.home/'media/conversation-inputs'
            if value not in queued and path.parent==root and path.resolve()==path and re.fullmatch('[0-9a-f]{32}[.](png|jpg)',path.name):path.unlink(missing_ok=True)
    fish.db.execute("UPDATE conversation_inbox SET images='[]' WHERE state!='queued'")


def cleanup_images(fish):
    root=fish.home/'media/conversation-inputs'
    if not root.is_dir() or root.is_symlink():return
    active={value for row in fish.rows("SELECT images FROM conversation_inbox WHERE state IN ('queued','working','sending')") for value in json.loads(row['images'] or '[]')}
    for path in root.iterdir():
        if path.is_symlink() or not path.is_file() or not re.fullmatch('[0-9a-f]{32}[.](png|jpg)',path.name):continue
        if str(path) not in active and path.stat().st_mtime<fish.clock()-300:path.unlink(missing_ok=True)


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
