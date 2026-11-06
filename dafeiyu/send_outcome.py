"""Interpret the installed CLI's structured send outcome without storing raw error payloads."""
import json
import re

UNKNOWN=('delivery_unknown','发送失败或结果不确定；不自动重复发送。')


def outcome(result):
    stdout=result.stdout or '';stderr=result.stderr or ''
    try:value=json.loads(stdout)
    except (ValueError,TypeError):value=None
    if result.returncode==0 and not isinstance(value,dict):return UNKNOWN
    nodes=[]
    def visit(node,depth=0):
        if not isinstance(node,dict) or depth>3:return
        nodes.append(node)
        for key in ('payload','result'):visit(node.get(key),depth+1)
    visit(value)
    # A partial dispatch must never become a context-triggered full resend.
    if any(node.get('sentBeforeError') is True or node.get('deliveryStatus')=='partial_failed' for node in nodes):return UNKNOWN
    if any(node.get('dryRun') is True for node in nodes):return ('delivery_unknown','仅返回演练结果，未确认实际发送。')
    if any('deliveryStatus' in node and node['deliveryStatus'] not in ('sent','suppressed','failed','partial_failed') for node in nodes):return UNKNOWN
    failed=result.returncode!=0 or any(node.get('ok') is False or node.get('success') is False or ('deliveryStatus' in node and node['deliveryStatus']!='sent') for node in nodes)
    if not failed:return ('accepted',None)
    hints=[]
    for node in nodes:
        for key in ('error','warning','hint','reason','suppressionReason'):
            item=node.get(key)
            if isinstance(item,str):hints.append(item)
            elif isinstance(item,dict):
                hints.extend(str(item[k]) for k in ('message','code','reason') if k in item)
    # Structured bodies may echo sent text: classify only error fields, not message content.
    if result.returncode!=0:
        hints.append(stderr)
        if not isinstance(value,dict):hints.append(stdout)
    details=' '.join(hints).lower()
    if any(word in details for word in ('context_token','context token','context expired','context is required')):return ('waiting_context','上下文失效；等待用户新消息。')
    if re.search(r'\b(?:unauthorized|forbidden|401|403)\b',details):return ('auth_failed','渠道认证失败，需本机检查登录。')
    return UNKNOWN
