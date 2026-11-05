"""Local single-user identity gate; no WeChat protocol or credential access."""
import signal
import argparse
import json
import sqlite3
import sys
import time
from .core import Fish, ModelError


def tables(fish):
    fish.db.executescript('''
    CREATE TABLE IF NOT EXISTS channel_binding (singleton INTEGER PRIMARY KEY CHECK(singleton=1),account TEXT,sender TEXT,last_seen REAL);
    CREATE TABLE IF NOT EXISTS channel_candidates (account TEXT,sender TEXT,created REAL,PRIMARY KEY(account,sender));
    CREATE TABLE IF NOT EXISTS inbound (id TEXT PRIMARY KEY,state TEXT,reply TEXT,created REAL);
    CREATE TABLE IF NOT EXISTS deliveries (outbox_id INTEGER PRIMARY KEY,state TEXT,error TEXT,updated REAL);
    ''')
    with fish.db:
        fish.db.execute("UPDATE inbound SET state='interrupted',reply='上次处理已中断，未自动重放。' WHERE state='running' AND created<?",(fish.clock()-120,))


def inbound(fish, event):
    tables(fish)
    if event.get('channel') != 'openclaw-weixin' or event.get('group') is not False:
        return '只支持绑定用户的微信文字私聊。'
    account, sender, message = (event.get(k) for k in ('account','sender','message_id'))
    if not all(isinstance(x,str) and x for x in (account,sender,message)):
        return '缺少稳定账号、发送者或消息编号，已停止处理。'
    binding = fish.db.execute('SELECT * FROM channel_binding WHERE singleton=1').fetchone()
    if not binding:
        with fish.db:
            fish.db.execute('INSERT OR REPLACE INTO channel_candidates VALUES (?,?,?)', (account,sender,fish.clock()))
        return '请在运行大肥鱼的电脑上确认微信身份绑定，确认前不会开放聊天记忆和任务。'
    if binding['account'] != account or binding['sender'] != sender:
        return '当前微信身份未绑定。'
    key = json.dumps([account,sender,message])
    with fish.db:
        fish.db.execute('UPDATE channel_binding SET last_seen=? WHERE singleton=1', (fish.clock(),))
        inserted = fish.db.execute("INSERT OR IGNORE INTO inbound VALUES (?,'running',NULL,?)", (key,fish.clock())).rowcount
        if not inserted:
            # Never repeat a tool call or resend a full reply on duplicate provider delivery.
            prior=fish.db.execute('SELECT state FROM inbound WHERE id=?',(key,)).fetchone()
            if prior['state']=='interrupted':return '上次处理已中断，未自动重放；请重新发送一个新请求。'
            return '这条消息已处理或正在处理中；任务结果可用「大肥鱼 /tasks」查看。'
    text=event.get('text','')
    if not isinstance(text,str) or not text.strip() or len(text)>12000:
        reply='只支持 1–12000 字符的文字消息。'
    else:
        if text.startswith('大肥鱼 '): text=text[len('大肥鱼 '):].strip()
        try:
            result=fish.command(text)
            reply=result if isinstance(result,str) else json.dumps(result,ensure_ascii=False,indent=2)
        except (ValueError,ModelError) as error: reply=str(error)
        except Exception: reply='处理失败；请在本机查看任务状态。'
    with fish.db:
        fish.db.execute("UPDATE inbound SET state='completed',reply=? WHERE id=?", (reply,key))
    return reply[:12000]


def main():
    def interrupted(_signum, _frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, interrupted)
    parser=argparse.ArgumentParser()
    parser.add_argument('--home',default='var')
    parser.add_argument('action',choices=['inbound','status','bind','unbind'])
    parser.add_argument('account',nargs='?');parser.add_argument('sender',nargs='?')
    args=parser.parse_args();fish=Fish(args.home);tables(fish)
    try:
        if args.action=='inbound':
            raw=sys.stdin.read(65537)
            if len(raw)>65536: raise ValueError('消息太大')
            print(json.dumps({'text':inbound(fish,json.loads(raw))},ensure_ascii=False))
        elif args.action=='status':
            print(json.dumps({'binding':fish.rows('SELECT * FROM channel_binding'),'candidates':fish.rows('SELECT * FROM channel_candidates')},ensure_ascii=False,indent=2))
        elif args.action=='bind':
            if not args.account or not args.sender: raise ValueError('需要账号和稳定 sender ID')
            candidate=fish.db.execute('SELECT * FROM channel_candidates WHERE account=? AND sender=?',(args.account,args.sender)).fetchone()
            if not candidate or candidate['created']<fish.clock()-600: raise ValueError('请先从微信发一条消息，并在 10 分钟内本机确认候选身份。')
            with fish.db:
                fish.db.execute('INSERT OR REPLACE INTO channel_binding VALUES (1,?,?,?)',(args.account,args.sender,0))
                fish.db.execute('DELETE FROM channel_candidates')
            print('已绑定。请从微信再次发送消息验证。')
        else:
            with fish.db: fish.db.execute('DELETE FROM channel_binding')
            print('已解除绑定，后台投递将停止。')
    finally: fish.close()


if __name__=='__main__':main()
