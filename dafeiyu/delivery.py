"""At-most-one attempt per result using the SDK-managed platform context. Never treats accepted as read."""
import json
from pathlib import Path
import subprocess
from datetime import datetime
from zoneinfo import ZoneInfo
from .channel import tables


def deliver(fish, runner=subprocess.run):
    tables(fish)
    now=fish.clock()
    with fish.db:
        fish.db.execute("UPDATE deliveries SET state='delivery_unknown' WHERE state='sending' AND updated<?",(now-90,))
        if fish.db.execute("SELECT value FROM settings WHERE key='paused'").fetchone()[0]=='1': return None
        from .presence import status as presence_status
        binding=fish.db.execute('SELECT * FROM channel_binding WHERE singleton=1').fetchone()
        if not binding: return None
        row=fish.db.execute('''SELECT o.*,t.kind FROM outbox o JOIN tasks t ON t.id=o.task_id
          LEFT JOIN deliveries d ON d.outbox_id=o.id WHERE o.seen=0 AND t.state IN ('succeeded','waiting_approval','failed')
          AND o.id NOT IN (SELECT outbox_id FROM curiosity_suppressed)
          AND (d.outbox_id IS NULL OR (d.state='waiting_context' AND d.updated<?)) ORDER BY CASE WHEN t.kind='reminder' THEN 0 ELSE 1 END,o.id LIMIT 1''',(binding['last_seen'],)).fetchone()
        if not row:return None
        if row['kind']!='reminder' and fish.db.execute("SELECT 1 FROM sqlite_master WHERE name='conversation_inbox'").fetchone() and fish.db.execute("SELECT 1 FROM conversation_inbox WHERE state IN ('queued','working','sending')").fetchone():return None
        if row['kind']!='reminder' and presence_status(fish)['mode']!='available':return None
        if row['kind'] in ('research','explore') and fish.db.execute("SELECT 1 FROM sqlite_master WHERE name='conversation_inbox'").fetchone() and fish.db.execute("SELECT 1 FROM conversation_inbox WHERE state IN ('accepted','interrupted') AND claimed>?",(now-120,)).fetchone():return None
        hour=datetime.fromtimestamp(now,ZoneInfo('Asia/Hong_Kong')).hour
        if row['kind']!='reminder' and (hour>=23 or hour<8):return None
        if fish.db.execute("SELECT 1 FROM deliveries WHERE state='accepted' AND updated>?",(now-30,)).fetchone():return None
        # Reserve before sending; crashes and timeouts never cause blind retries.
        claimed=fish.db.execute("INSERT OR IGNORE INTO deliveries VALUES (?,'sending',NULL,?)",(row['id'],now)).rowcount
        if not claimed:
            claimed=fish.db.execute("UPDATE deliveries SET state='sending',updated=? WHERE outbox_id=? AND state='waiting_context'",(now,row['id'])).rowcount
        if not claimed:return None
        from .sharing import peer_digest
        fish.db.execute('INSERT OR REPLACE INTO delivery_peers VALUES (?,?)',(row['id'],peer_digest(binding)))
    script=Path(__file__).resolve().parent.parent/'scripts/openclaw'
    message=(('🐳 任务 '+row['task_id']+'\n') if row['kind'] not in ('explore','research','platform') else '')+row['content'][:2500]
    if len(row['content'])>2500:message+='\n完整成果：大肥鱼 /result '+row['task_id']
    command=[str(script),'message','send','--channel','openclaw-weixin','--account',binding['account'],'--target',binding['sender'],'--message',message,'--json']
    asset=fish.db.execute('SELECT path FROM task_assets WHERE task_id=?',(row['task_id'],)).fetchone()
    if asset:
        path=Path(asset['path']);root=fish.home/'media/outbound'
        if not path.is_absolute() or path.resolve()!=path or not path.is_relative_to(root) or not path.is_file() or not 44<path.stat().st_size<=10*1024*1024:
            with fish.db:fish.db.execute("UPDATE deliveries SET state='asset_missing',error='音频附件已失效，请重新生成。',updated=? WHERE outbox_id=?",(now,row['id']))
            return 'asset_missing'
        command+=['--media',str(path)]
    state='delivery_unknown';error=None
    try:
        result=runner(command,capture_output=True,text=True,timeout=60)
        # Re-check binding before future attempts. In-flight send has already been admitted.
        if result.returncode==0:
            try: json.loads(result.stdout);state='accepted'
            except ValueError:error='发送返回格式异常，投递结果不确定。'
        else:
            combined=(result.stdout+result.stderr).lower()
            if any(term in combined for term in ('context_token','context token','context expired','context is required')):
                state='waiting_context';error='上下文失效；等待用户新消息。'
            elif any(term in combined for term in ('unauthorized','forbidden','401','403')):
                state='auth_failed';error='渠道认证失败，需本机检查登录。'
            else:error='发送失败或结果不确定；不自动重复发送。'
    except (OSError,subprocess.TimeoutExpired):error='发送超时或进程失败，结果不确定；不自动重复发送。'
    with fish.db:
        fish.db.execute('UPDATE deliveries SET state=?,error=?,updated=? WHERE outbox_id=?',(state,error,fish.clock(),row['id']))
    return state
