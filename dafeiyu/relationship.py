"""Small, dated context from actual user utterances and task results. No inferred profile."""
from datetime import datetime
from zoneinfo import ZoneInfo
import json
import re
from .memory import reject_secret


def context(fish,query=None):
    now=fish.clock();days=set();anchors=[]
    rows=fish.rows("SELECT id,content,created FROM messages WHERE role='user' AND created>? AND length(content)>=12 AND substr(content,1,1)!='/' ORDER BY id DESC LIMIT 100",(now-14*86400,))
    for row in rows:
        date=datetime.fromtimestamp(row['created'],ZoneInfo('Asia/Hong_Kong'))
        day=date.strftime('%Y-%m-%d')
        if day in days:continue
        try:reject_secret(row['content'])
        except ValueError:continue
        days.add(day);anchors.append({'message_id':row['id'],'at':date.isoformat(),'user_quote':row['content'][:240],'status':'用户当时说过的话，不是永久事实或当前状态'})
        if len(anchors)>=(3 if query is None or re.search("记得|昨天|上次|前天|之前",query) else 1):break
    tasks=[]
    for row in ([] if query is not None and not re.search('查|任务|结果|进度|刚才|之前|做完|怎么样|那件事|那个|上次',query) else fish.rows("SELECT id,kind,goal,state,result,error,created FROM tasks WHERE created>? AND kind IN ('research','explore','browser','video','reminder','speech') ORDER BY created DESC LIMIT 3",(now-3*86400,))):
        goal=row['goal']
        if row['kind']=='video':
            try:goal=json.loads(goal).get('question','短视频采样')
            except ValueError:goal='短视频采样'
        try:reject_secret(goal+' '+(row['result'] or ''))
        except ValueError:continue
        tasks.append({'id':row['id'],'kind':row['kind'],'goal':goal[:160],'state':row['state'],'result_excerpt':(row['result'] or '')[:280],'error':(row['error'] or '')[:180],
                      'at':datetime.fromtimestamp(row['created'],ZoneInfo('Asia/Hong_Kong')).isoformat()})
    return {'过去真实原话（可过时，不推断性格）':anchors,'最近任务实际状态（成功不等于送达）':tasks}


def task_reply(fish):
    tasks=context(fish)['最近任务实际状态（成功不等于送达）']
    if not tasks:return '本鱼这几天没有找到研究或提醒任务。更早的记录可以用 /tasks 看看。'
    labels={'queued':'还在排队','running':'正在做','succeeded':'已经做完','failed':'这次没完成','cancelled':'已经取消','waiting_approval':'等你确认'}
    lines=[]
    for row in tasks:
        text='「'+row['goal'][:70]+'」'+labels.get(row['state'],row['state'])+'。'
        if row['state']=='failed':text+=row['error']
        elif row['state']=='succeeded':text+=row['result_excerpt'][:180]+'\n完整内容：/result '+row['id']
        lines.append(text)
    return '本鱼看了实际记录：\n\n'+'\n\n'.join(lines)
