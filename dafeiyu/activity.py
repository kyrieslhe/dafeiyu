"""Today's recorded activity, with pending work and channel acceptance kept separate."""
from datetime import datetime
from zoneinfo import ZoneInfo
from .sharing import cutoff,sent_context

TZ=ZoneInfo('Asia/Hong_Kong')


def day(fish):
    now=fish.clock();date=datetime.fromtimestamp(now,TZ);start=max(date.replace(hour=0,minute=0,second=0,microsecond=0).timestamp(),cutoff(fish,1))
    completed=fish.rows('''SELECT n.task_id,coalesce(s.topic,n.topic) topic,substr(n.summary,1,350) summary,n.created
      FROM exploration_notes n LEFT JOIN interest_steps s ON s.task_id=n.task_id
      WHERE n.created>? AND n.created<=? ORDER BY n.created DESC LIMIT 4''',(start,now))
    for row in completed:
        row['completed_at']=datetime.fromtimestamp(row.pop('created'),TZ).isoformat()
        row['scope']='实际探索结果，按正文区分仅目录、文字或采样，不代表完整观看或微信送达'
    starts=fish.rows('''SELECT r.task_id,t.state,r.started FROM curiosity_runs r JOIN tasks t ON t.id=r.task_id
      WHERE r.started>? AND r.started<=? ORDER BY r.started DESC LIMIT 4''',(start,now))
    for row in starts:row['started_at']=datetime.fromtimestamp(row.pop('started'),TZ).isoformat()
    queued=fish.db.execute("SELECT count(*) FROM tasks WHERE kind='explore' AND state='queued' AND created>?",(start,)).fetchone()[0]
    added=fish.rows('SELECT topic,reason,created FROM interest_growth WHERE created>? AND created<=? ORDER BY created DESC LIMIT 2',(start,now))
    for row in added:row['added_at']=datetime.fromtimestamp(row.pop('created'),TZ).isoformat()
    accepted=[row for row in sent_context(fish) if row['accepted_at'][:10]==date.strftime('%Y-%m-%d')]
    return {'date':date.strftime('%Y-%m-%d'),'timezone':'Asia/Hong_Kong','completed_explorations':completed,'actual_random_starts':starts,'queued_explorations':queued,'new_public_interests':added,'channel_accepted_notices':accepted,'scope':'只描述今天且清空背景后的真实记录；排队不等于完成，启动不等于成功，渠道接受不等于送达或已读。没有记录不编造一整天的生活。'}
