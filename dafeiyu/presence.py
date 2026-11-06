"""Temporary availability from explicit messages; never an inferred emotional profile."""
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
import json
import re


def set_quiet(fish,mode,until):
    fish.db.execute("INSERT OR REPLACE INTO settings VALUES ('presence_state',?)",(json.dumps({'mode':mode,'until':until}),))


def status(fish):
    row=fish.db.execute("SELECT value FROM settings WHERE key='presence_state'").fetchone()
    value=json.loads(row['value']) if row else {'mode':'available','until':0}
    if value['until'] is not None and value['until']<=fish.clock():return {'mode':'available','until':0}
    return value


def observe(fish,text):
    value=text.strip()
    # A new actual message means the user has returned, unless it explicitly closes the chat.
    set_quiet(fish,'available',0)
    if '?' in value or '？' in value or re.search('不是|不要睡|不想睡|没睡|别说',value):return
    if re.match(r'^(晚安[呀啦哟~～！!。\s]*$|我(?:先|要|准备|现在要|打算|得)?(?:去)?睡觉)',value):
        now=datetime.fromtimestamp(fish.clock(),ZoneInfo('Asia/Hong_Kong'))
        wake=now.replace(hour=9,minute=0,second=0,microsecond=0)
        if wake<=now:wake+=timedelta(days=1)
        set_quiet(fish,'resting',wake.timestamp())
    elif re.match(r'^(?:我(?:先|现在|要|准备|打算|得|去|出门|出去){0,3}(?:忙|开会|跑步|上课)|先不聊了)',value):set_quiet(fish,'busy',fish.clock()+2*3600)
    elif re.match(r'^(?:先)?(?:别打扰我|不要打扰我)',value):set_quiet(fish,'quiet',None)


def command(fish,argument):
    if argument=='off':
        with fish.db:set_quiet(fish,'available',0)
        return '好，本鱼恢复正常分享；静默时段和每日上限仍然生效。'
    if argument:
        try:minutes=int(argument)
        except ValueError:raise ValueError('用法：/quiet 1–1440（分钟），或 /quiet off') from None
        if not 1<=minutes<=1440:raise ValueError('安静时间须为 1–1440 分钟。')
        with fish.db:set_quiet(fish,'quiet',fish.clock()+minutes*60)
        return '好，这段时间本鱼不主动打扰；你发消息回来时就恢复聊天。'
    return status(fish)
