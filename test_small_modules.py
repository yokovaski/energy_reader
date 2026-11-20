import unittest
from unittest import mock

import enums
import redis_queue
from read_handler_interface import ReadHandlerInterface


class EnumsTests(unittest.TestCase):
    def test_values(self):
        self.assertEqual('READER', enums.Thread.READER.value)
        self.assertEqual('RUNNING', enums.Status.RUNNING.value)
        self.assertEqual('SOLAR_API', enums.Error.SOLAR_API.value)


class ReadHandlerInterfaceTests(unittest.TestCase):
    def test_defaults_do_nothing(self):
        handler = ReadHandlerInterface()
        self.assertIsNone(handler.handle_read({}))
        self.assertIsNone(handler.get_name())
        self.assertIsNone(handler.seconds_since_last_run_time())


class RedisQueueTests(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch('redis_queue.redis.Redis')
        self.redis = patcher.start().return_value
        self.addCleanup(patcher.stop)
        self.queue = redis_queue.RedisQueue('normal')

    def test_key_uses_namespace(self):
        self.assertEqual('queue:normal', self.queue.key)
        self.assertEqual('other:x', redis_queue.RedisQueue('x', namespace='other').key)

    def test_size_and_empty(self):
        self.redis.llen.return_value = 2
        self.assertEqual(2, self.queue.qsize())
        self.assertFalse(self.queue.empty())
        self.redis.llen.return_value = 0
        self.assertTrue(self.queue.empty())

    def test_put_pushes_right(self):
        self.queue.put('a')
        self.redis.rpush.assert_called_once_with('queue:normal', 'a')

    def test_blocking_get_returns_value_part(self):
        self.redis.blpop.return_value = ('queue:normal', b'a')
        self.assertEqual(b'a', self.queue.get(timeout=3))
        self.redis.blpop.assert_called_once_with('queue:normal', timeout=3)

    def test_non_blocking_get(self):
        self.redis.lpop.return_value = (b'k', b'v')
        self.assertEqual(b'v', self.queue.get_nowait())

    def test_get_on_empty_queue_returns_none(self):
        self.redis.lpop.return_value = None
        self.assertIsNone(self.queue.get(block=False))


if __name__ == '__main__':
    unittest.main()
