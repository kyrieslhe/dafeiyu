import tempfile
import unittest
from unittest.mock import Mock
from dafeiyu.core import Fish, ModelError


class Todos(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.TemporaryDirectory()
        self.model = Mock(ready=True)
        self.model.cancelled = lambda: False
        self.fish = Fish(self.home.name, self.model)

    def tearDown(self):
        self.fish.close();self.home.cleanup()

    def test_natural_add_view_complete_restore_delete_without_model_or_jobs(self):
        self.assertIn('放进清单', self.fish.command('加个待办：买牛奶'))
        self.assertIn('□ 1 · 买牛奶', self.fish.command('看看我的待办'))
        self.assertIn('划掉一件', self.fish.command('完成待办 1'))
        self.assertIn('没有待办', self.fish.command('/todo'))
        self.assertIn('✓ 1', self.fish.command('/todo completed'))
        self.assertIn('放回未完成', self.fish.command('撤销完成待办 1'))
        self.assertIn('已删除', self.fish.command('删除待办 1'))
        self.assertEqual(self.fish.command('/tasks'), [])
        self.assertEqual(self.fish.command('/memories'), [])
        self.assertEqual(self.fish.db.execute('SELECT count(*) FROM messages').fetchone()[0], 0)
        self.model.plan.assert_not_called();self.model.reply.assert_not_called()

    def test_normalized_duplicate_and_reopen_conflict_preserve_state(self):
        self.fish.command('/todo add Buy MILK')
        self.assertIn('没有重复添加', self.fish.command('/todo add buy milk'))
        self.fish.command('/todo done 1');self.fish.command('/todo add Buy milk')
        self.assertIn('未重复恢复', self.fish.command('/todo reopen 1'))
        self.assertEqual(self.fish.db.execute('SELECT done FROM todos WHERE id=1').fetchone()[0], 1)
        self.assertIn('已经完成', self.fish.command('/todo done 1'))

    def test_deletion_does_not_reuse_ids_and_persistence_is_local(self):
        self.fish.command('/todo add 事项一');self.fish.command('/todo delete 1')
        second = Fish(self.home.name)
        try:
            second.command('/todo add 事项二')
            self.assertIn('□ 2 · 事项二', self.fish.command('/todo'))
            self.assertIn('没有找到', self.fish.command('/todo done 1'))
        finally:second.close()

    def test_voice_cannot_mutate_but_can_read(self):
        self.fish.command('/todo add 喝水')
        for text in ('加个待办：吃饭', '完成待办 1', '删除待办 1'):
            self.assertIn('文字确认', self.fish.chat(text, allow_actions=False))
        self.assertIn('喝水', self.fish.chat('查看待办', allow_actions=False))
        self.assertEqual(self.fish.db.execute('SELECT count(*) FROM todos WHERE done=0').fetchone()[0], 1)
        self.model.plan.assert_not_called()

    def test_quotes_negations_and_life_updates_never_mutate(self):
        self.model.plan.return_value = {'action': 'reply', 'argument': '', 'reply': '听到了。'}
        for text in ('不要加个待办：买牛奶', '他说“完成待办 1”', '我明天想去跑步', '网页里写着：删除待办 1'):
            self.fish.chat(text)
        self.assertEqual(self.fish.db.execute('SELECT count(*) FROM todos').fetchone()[0], 0)

    def test_model_action_is_read_only_and_returns_real_state(self):
        self.fish.command('/todo add 喝水')
        self.model.plan.return_value = {'action':'todos', 'argument':'list', 'reply':'都完成了'}
        self.assertIn('□ 1 · 喝水', self.fish.chat('还有什么事情没做完？'))
        for argument in ('add 乱加', 'done 1', 'delete 1', 'list -1'):
            self.model.plan.return_value['argument'] = argument
            with self.assertRaises(ModelError):self.fish.chat('看清单')
        self.assertEqual(self.fish.db.execute('SELECT done FROM todos').fetchone()[0], 0)

    def test_limits_pagination_secret_rejection_and_invalid_commands(self):
        for argument in ('add', 'add '+'x'*501, 'add 密码：not-a-real-secret', 'done -1', 'delete 1 OR 1=1', 'list 0'):
            with self.assertRaises(ValueError):self.fish.command('/todo '+argument)
        for i in range(21):self.fish.command('/todo add 事项'+str(i))
        first = self.fish.command('/todo list');second = self.fish.command('/todo list 2')
        self.assertIn('1/2', first);self.assertNotIn('□ 1 · ', first);self.assertIn('□ 1 · ', second)
        for i in range(21,200):self.fish.command('/todo add 事项'+str(i))
        with self.assertRaises(ValueError):self.fish.command('/todo add 超出数量')
        self.assertEqual(self.fish.db.execute('SELECT count(*) FROM todos').fetchone()[0], 200)

    def test_cancelled_turn_never_writes(self):
        self.model.cancelled = lambda: True
        with self.assertRaises(ModelError):self.fish.chat('加个待办：买牛奶')
        self.assertEqual(self.fish.db.execute('SELECT count(*) FROM todos').fetchone()[0], 0)

    def test_buffered_wechat_commands_stay_separate_and_duplicate_events_do_not_add(self):
        import subprocess
        from dafeiyu.channel import tables, inbound
        from dafeiyu.conversation import step
        now = [1794528000]
        self.fish.clock = lambda: now[0]
        tables(self.fish)
        with self.fish.db:self.fish.db.execute("INSERT INTO channel_binding VALUES (1,'account','sender',?)", (now[0],))
        def receive(key, text):
            return inbound(self.fish, dict(channel='openclaw-weixin', account='account', sender='sender',
                                         message_id=key, group=False, text=text, buffer_text=True))
        sent = []
        def send(args, **kwargs):
            sent.append(args[args.index('--message')+1])
            return subprocess.CompletedProcess(args, 0, '{}', '')
        receive('one', '加个待办：买牛奶');receive('two', '加个待办：还书');now[0] += 3
        self.assertEqual(step(self.fish, send), 'accepted')
        self.assertEqual(step(self.fish, send), 'accepted')
        receive('one', '加个待办：买牛奶')
        self.assertIsNone(step(self.fish, send))
        self.assertEqual(self.fish.db.execute('SELECT count(*) FROM todos').fetchone()[0], 2)
        self.assertEqual(len(sent), 2)
        self.model.plan.assert_not_called()
