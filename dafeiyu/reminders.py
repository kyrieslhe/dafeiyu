"""Read actual reminder deadlines and explicitly move only unclaimed reminders."""
import math
import re
from datetime import datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo('Asia/Hong_Kong')


def listing(fish, page='1'):
    if not re.fullmatch(r'[1-9][0-9]{0,5}', page):raise ValueError('用法：/reminders [页码]')
    count = fish.db.execute("SELECT count(*) FROM tasks WHERE kind='reminder' AND state IN ('queued','running')").fetchone()[0]
    if not count:return '目前没有待触发或正在处理的提醒。🐳'
    pages = (count+9)//10
    if int(page)>pages:return '这页没有提醒；共 '+str(pages)+' 页。'
    rows = fish.rows("SELECT id,goal,due,state FROM tasks WHERE kind='reminder' AND state IN ('queued','running') ORDER BY due,id LIMIT 10 OFFSET ?", ((int(page)-1)*10,))
    lines=[]
    for row in rows:
        when=datetime.fromtimestamp(row['due'],TZ).strftime('%Y-%m-%d %H:%M:%S')
        status='正在处理' if row['state']=='running' else ('已到时间，待处理' if row['due']<=fish.clock() else '待触发')
        lines.append(when+' 香港时间 · '+status+'\n'+row['goal'][:200]+'\n编号 '+row['id'])
    return '你的提醒（第 '+page+'/'+str(pages)+' 页，共 '+str(count)+' 条）：\n\n'+'\n\n'.join(lines)+'\n\n离线时不会准时执行；以上不是已送达记录。'


def reschedule(fish, argument):
    identifier, _, value = argument.strip().partition(' ')
    if not re.fullmatch(r'[a-f0-9]{12}',identifier):raise ValueError('用法：/reschedule 提醒编号 ISO8601时间')
    try:
        when=datetime.fromisoformat(value)
        if when.tzinfo is None:when=when.replace(tzinfo=TZ)
        due=when.timestamp()
        if not math.isfinite(due) or due<=fish.clock():raise ValueError()
    except (ValueError,OverflowError,OSError):raise ValueError('请提供未来的有效时间，如 2026-12-01T09:00；未带时区时按香港时间。') from None
    with fish.db:
        changed=fish.db.execute("UPDATE tasks SET due=? WHERE id=? AND kind='reminder' AND state='queued'",(due,identifier)).rowcount
    if not changed:return '未修改：该提醒不存在、已开始处理或已经结束。正在处理的提醒不能改期。'
    return '提醒时间改好啦：'+when.astimezone(TZ).isoformat()+'（香港时间）\n编号 '+identifier


def parse(text):
    text=text.strip()
    if text in ('查看提醒','我的提醒','看看我的提醒','提醒清单','我有哪些提醒','接下来有哪些提醒'):
        return 'list','1'
    match=re.fullmatch(r'修改提醒\s+([a-f0-9]{12})\s+(?:到|为)\s*(\S+)',text)
    if match:return 'reschedule',match.group(1)+' '+match.group(2)
    return None


def natural(fish,text,allow_writes=True):
    request=parse(text)
    if request is None:return None
    operation,argument=request
    if operation=='list':return listing(fish,argument)
    if not allow_writes:return '改提醒时间请用文字确认，例如「修改提醒 编号 到 2026-12-01T09:00」。'
    return reschedule(fish,argument)
