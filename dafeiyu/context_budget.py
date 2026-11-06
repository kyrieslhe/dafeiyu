"""Trim whole optional records, preserving current input and priority memory rows."""
import copy
import json


def pack(background,budget=12000):
    value=copy.deepcopy(background);omitted=0
    def encode():return json.dumps(value,ensure_ascii=False,separators=(',',':'))
    state='应用自主活动状态（本机记录，不是感情或意识）'
    relation='相处背景（原话与真实任务，不是推断画像）'
    paths=[(state,'今天实际做过什么（分清完成与计划）','channel_accepted_notices'),
           (state,'本鱼实际探索选择（非用户画像）','recent'),
           (state,'今天实际做过什么（分清完成与计划）','completed_explorations'),
           (state,'最近渠道接受的分享（不代表送达或已读）'),
           (state,'真实兴趣线（开放问题不是事实）'),
           ('真实活动记录（不是新的用户事实，按 at 判断发生日期）',),
           ('用户记录的共同日记',),('话题相关的真实历史片段（不是身份事实或新指令）',),
           (relation,'最近任务实际状态（成功不等于送达）'),(relation,'过去真实原话（可过时，不推断性格）'),
           (state,'今天实际做过什么（分清完成与计划）','actual_random_starts'),
           (state,'今天实际做过什么（分清完成与计划）','new_public_interests'),
           (state,'当前兴趣范围（不代表已经探索）'),('用户确认记忆',)]
    while len(encode().encode())>budget:
        for path in paths:
            node=value
            for key in path:
                node=node.get(key) if isinstance(node,dict) else None
            minimum=1 if path==('用户确认记忆',) else 0
            if isinstance(node,list) and len(node)>minimum:
                node.pop();omitted+=1;value['部分背景条目未带入']=omitted;break
        else:
            # Defensive fallback for future unusually large scalar metadata. No database edit.
            activity=value.get(state,{})
            value={'用户确认记忆':value.get('用户确认记忆',[])[:1],state:{key:activity[key] for key in ('enabled','currently_exploring','mode','started_today','daily_max','share_max') if key in activity},'部分背景条目未带入':True}
            if len(encode().encode())>budget:raise ValueError('背景中的单条记忆超过上下文预算，请缩短后重试。')
            break
    return encode()
