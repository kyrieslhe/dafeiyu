"""Bounded on-demand result pages; never enqueue extra platform messages."""
PAGE_SIZE=2400


def pages(text):
    result=[]
    while len(text)>PAGE_SIZE:
        boundary=text.rfind('\n',PAGE_SIZE//2,PAGE_SIZE)
        end=boundary+1 if boundary>=0 else PAGE_SIZE
        result.append(text[:end]);text=text[end:]
    result.append(text)
    return result


def read(fish,argument):
    parts=argument.split()
    if not 1<=len(parts)<=2:return '用法：/result 任务编号 [页码]'
    try:
        page=int(parts[1]) if len(parts)==2 else 1
        if page<1:raise ValueError()
    except ValueError:return '页码须为从 1 开始的整数。'
    row=fish.db.execute('SELECT state,result,error FROM tasks WHERE id=?',(parts[0],)).fetchone()
    if row is None:return '没有这个任务。'
    content=row['result'] or row['error'] or '暂时没有成果，任务状态：'+row['state']
    chunks=pages(content)
    if page>len(chunks):return '共 '+str(len(chunks))+' 页，请选择有效页码。'
    reply='🐳 任务 '+parts[0]+' · '+row['state']+' · 第 '+str(page)+'/'+str(len(chunks))+' 页\n\n'+chunks[page-1]
    if page<len(chunks):reply+='\n\n下一页：大肥鱼 /result '+parts[0]+' '+str(page+1)
    return reply
