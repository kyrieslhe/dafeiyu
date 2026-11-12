"""Explicit personal checklist, separate from model jobs and inferred memories."""
import re
from .memory import fingerprint, reject_secret

PAGE = 20
HELP = '用法：/todo add 内容；/todo list|completed|all [页码]；/todo done|reopen|delete 编号'


def initialize(fish):
    fish.db.execute('''CREATE TABLE IF NOT EXISTS todos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,content TEXT NOT NULL,normalized TEXT NOT NULL,
        done INTEGER NOT NULL DEFAULT 0,created REAL NOT NULL,updated REAL NOT NULL)''')
    fish.db.commit()


def command(fish, argument):
    operation, _, value = argument.strip().partition(' ')
    value = value.strip()
    operation = operation or 'list'
    if operation in ('list', 'completed', 'all'):
        if value and (not re.fullmatch(r'[1-9][0-9]{0,5}', value)):raise ValueError(HELP)
        page = int(value or '1')
        where = {'list': 'WHERE done=0', 'completed': 'WHERE done=1', 'all': ''}[operation]
        count = fish.db.execute('SELECT count(*) FROM todos '+where).fetchone()[0]
        pages = max(1, (count+PAGE-1)//PAGE)
        if page > pages:return '这页没有待办；共 '+str(pages)+' 页。'
        rows = fish.rows('SELECT id,content,done FROM todos '+where+' ORDER BY id DESC LIMIT ? OFFSET ?', (PAGE, (page-1)*PAGE))
        if not rows:return '目前没有'+('已完成的' if operation == 'completed' else '')+'待办。🐳'
        lines = [('✓ ' if row['done'] else '□ ')+str(row['id'])+' · '+row['content'] for row in rows]
        return '你的待办（第 '+str(page)+'/'+str(pages)+' 页，共 '+str(count)+' 条）：\n'+'\n'.join(lines)
    if operation not in ('add', 'done', 'reopen', 'delete'):raise ValueError(HELP)
    with fish.db:
        # Serialize duplicate detection and state changes across the gateway and conversation worker.
        fish.db.execute("UPDATE settings SET value=value WHERE key='paused'")
        if operation == 'add':
            if not value or len(value)>500:raise ValueError('每条待办须为 1–500 字符。')
            reject_secret(value)
            normalized = fingerprint(value)
            duplicate = fish.db.execute('SELECT id FROM todos WHERE normalized=? AND done=0', (normalized,)).fetchone()
            if duplicate:return '这条还在清单里：待办 '+str(duplicate[0])+'，没有重复添加。'
            if fish.db.execute('SELECT count(*) FROM todos').fetchone()[0]>=200:
                raise ValueError('清单最多保存 200 条，请先删除不再需要的已完成事项。')
            now = fish.clock()
            identifier = fish.db.execute('INSERT INTO todos(content,normalized,created,updated) VALUES (?,?,?,?)', (value,normalized,now,now)).lastrowid
            return '放进清单啦：'+value+' 📝\n待办 '+str(identifier)+'；完成后说「完成待办 '+str(identifier)+'」。'
        if not re.fullmatch(r'[1-9][0-9]{0,12}', value):raise ValueError(HELP)
        identifier = int(value)
        row = fish.db.execute('SELECT content,normalized,done FROM todos WHERE id=?', (identifier,)).fetchone()
        if not row:return '没有找到待办 '+value+'，没有改动清单。'
        if operation == 'delete':
            fish.db.execute('DELETE FROM todos WHERE id=?', (identifier,))
            return '已删除待办 '+value+'。已有备份需单独清理。'
        done = int(operation == 'done')
        if row['done'] == done:return '待办 '+value+('已经完成啦。' if done else '已经在未完成清单里啦。')
        if not done and fish.db.execute('SELECT 1 FROM todos WHERE normalized=? AND done=0 AND id!=?', (row['normalized'],identifier)).fetchone():
            return '未完成清单已有相同事项，未重复恢复。'
        fish.db.execute('UPDATE todos SET done=?,updated=? WHERE id=?', (done,fish.clock(),identifier))
        return ('划掉一件，干得漂亮！✓ ' if done else '已放回未完成清单：')+row['content']+'\n待办 '+value


def parse(text):
    """Only full, explicit requests; quotations and ordinary life updates do not mutate."""
    text = text.strip()
    if text in ('看看待办', '查看待办', '我的待办', '待办清单', '看看我的待办', '我还有哪些待办', '我还有哪些待办？'):
        return 'list'
    if text in ('查看已完成待办', '看看已完成待办'):return 'completed'
    match = re.fullmatch(r'(?:帮我)?(?:加个|加一条|添加|新增)待办[：: ]+([^\n]+)', text)
    argument = 'add '+match.group(1) if match else None
    if argument is None:
        match = re.fullmatch(r'(完成|恢复|撤销完成|删除)待办\s*([1-9][0-9]{0,12})[。！!]?', text)
        if match:argument = {'完成':'done','恢复':'reopen','撤销完成':'reopen','删除':'delete'}[match.group(1)]+' '+match.group(2)
    return argument


def natural(fish, text, allow_writes=True):
    argument = parse(text)
    if argument is None:return None
    if argument in ('list', 'completed'):return command(fish, argument)
    if not allow_writes:return '本鱼听到了。清单改动请用文字确认，例如「加个待办：买牛奶」。'
    return command(fish, argument)
