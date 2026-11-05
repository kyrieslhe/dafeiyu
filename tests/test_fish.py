import tempfile
import unittest
from dafeiyu.core import Fish, ModelError


class FakeModel:
    ready = True
    def reply(self, messages):
        return '测试模型回复'


class FishTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.now = 1793836800.0
        self.fish = Fish(self.tmp.name, FakeModel(), lambda: self.now)

    def tearDown(self):
        self.fish.close()
        self.tmp.cleanup()

    def test_daily_once_and_offline_catchup(self):
        self.fish.command('/routine 00:00 根据已有记忆写札记')
        self.fish.tick()
        self.assertEqual(len(self.fish.command('/inbox')), 1)
        self.fish.tick()
        self.assertEqual(len(self.fish.command('/inbox')), 1)
        self.now += 4 * 86400
        self.fish.tick()
        self.assertEqual(len(self.fish.command('/inbox')), 2)
        self.fish.tick()
        self.assertEqual(len(self.fish.command('/inbox')), 2)

    def test_routine_pause_and_delete(self):
        self.fish.command('/routine 00:00 札记')
        self.fish.command('/pause')
        self.fish.tick()
        self.assertEqual(self.fish.command('/tasks'), [])
        self.fish.command('/unroutine 1')
        self.fish.command('/resume')
        self.fish.tick()
        self.assertEqual(self.fish.command('/tasks'), [])

    def test_restart_memory_and_chat(self):
        self.fish.remember('喜欢简洁中文')
        self.fish.chat('你好')
        self.fish.close()
        self.fish = Fish(self.tmp.name, FakeModel(), lambda: self.now)
        self.assertIn('喜欢简洁中文', str(self.fish.context('继续')))
        self.assertEqual(len(self.fish.rows('SELECT * FROM messages')), 2)

    def test_forget_removes_context(self):
        self.fish.remember('秘密偏好')
        self.fish.chat('秘密偏好')
        self.fish.command('/diary 秘密偏好')
        self.fish.forget(1)
        self.assertNotIn('秘密偏好', str(self.fish.context('你好')))

    def test_due_and_outbox_once_after_restart(self):
        identifier = self.fish.enqueue('reminder', '喝水', self.now+60)
        self.assertIsNone(self.fish.tick())
        self.now += 120
        self.assertEqual(self.fish.tick(), identifier)
        self.assertIsNone(self.fish.tick())
        self.fish.close()
        self.fish = Fish(self.tmp.name, FakeModel(), lambda: self.now)
        self.assertIsNone(self.fish.tick())
        self.assertEqual(len(self.fish.command('/inbox')), 1)
        self.fish.command('/ack 1')
        self.assertEqual(self.fish.command('/inbox'), [])

    def test_pause_cancel(self):
        identifier = self.fish.enqueue('reminder', '取消我')
        self.fish.command('/pause')
        self.assertIsNone(self.fish.tick())
        self.fish.command('/cancel '+identifier)
        self.fish.command('/resume')
        self.assertIsNone(self.fish.tick())
        self.assertEqual(self.fish.command('/inbox'), [])

    def test_model_failure_does_not_forge_success(self):
        class Failed:
            ready = True
            def reply(self, messages):
                raise ModelError('额度不足')
        self.fish.model = Failed()
        self.fish.enqueue('draft', '主题')
        self.fish.tick()
        self.assertEqual(self.fish.command('/tasks')[0]['state'], 'failed')
        self.assertEqual(len(self.fish.command('/inbox')),1)
        self.assertIn('没有完成',self.fish.command('/inbox')[0]['content'])
        with self.assertRaises(ModelError):
            self.fish.chat('你好')
        self.assertEqual(self.fish.rows('SELECT * FROM messages'), [])

    def test_expired_lease_never_reruns(self):
        identifier = self.fish.enqueue('draft', '主题')
        with self.fish.db:
            self.fish.db.execute("UPDATE tasks SET state='running',lease=? WHERE id=?", (self.now-1, identifier))
        self.fish.tick()
        self.assertEqual(self.fish.command('/tasks')[0]['state'], 'failed')

    def test_limit_and_invalid_inputs(self):
        for _ in range(10):
            self.fish.enqueue('reminder', '喝水')
        with self.assertRaises(ValueError):
            self.fish.enqueue('reminder', '超额')
        with self.assertRaises(ValueError):
            self.fish.remember('')
        with self.assertRaises(ValueError):
            self.fish.command('/remind invalid 内容')

    def test_cancel_during_model_call_discards_result(self):
        fish = self.fish
        identifier = fish.enqueue('draft', '主题')
        class Cancelling:
            def reply(self, messages):
                fish.command('/cancel ' + identifier)
                return '不应该发布'
        fish.model = Cancelling()
        fish.tick()
        self.assertEqual(fish.command('/tasks')[0]['state'], 'cancelled')
        self.assertEqual(fish.command('/inbox'), [])


if __name__ == '__main__':
    unittest.main()
