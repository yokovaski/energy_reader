import json
import os
import tempfile
import unittest
from unittest import mock

import redis_pusher
from fakes import FakeRedisQueue


class RedisPusherTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        state = mock.patch('redis_pusher.STATE_FILE', os.path.join(self.dir.name, 'state.json'))
        state.start()
        self.addCleanup(state.stop)

        patcher = mock.patch('redis_pusher.RedisQueue', side_effect=lambda name: FakeRedisQueue(name))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.logger = mock.Mock()
        self.pusher = redis_pusher.RedisPusher(self.logger, ['portal', 'other'])

    def test_queue_per_portal(self):
        self.assertEqual(['queue:normal_portal', 'queue:normal_other'], [q.key for q in self.pusher.redis_queues])

    def test_pushes_copy_without_all_solar_and_with_extra_solar_added(self):
        data = {'solarNow': 1000, 'solarTotal': 5000, 'allSolar': {'pac': 1000},
                'extraSolar': {'pac': 150, 'totalEnergy': 100}}

        self.pusher.handle_read(data)

        for queue in self.pusher.redis_queues:
            self.assertEqual({'solarNow': 1150, 'solarTotal': 5000}, json.loads(queue.items[0]))
        self.assertIn('allSolar', data)  # other handlers still get the original
        self.assertIn('extraSolar', data)
        self.assertEqual(1000, data['solarNow'])

    def test_state_is_stored_in_the_patched_location(self):
        self.pusher.handle_read({'solarNow': 0, 'solarTotal': 1, 'allSolar': {},
                                 'extraSolar': {'pac': 0, 'totalEnergy': 100}})
        self.assertEqual(['state.json'], os.listdir(self.dir.name))

    def test_failing_queue_is_logged_and_others_still_get_data(self):
        self.pusher.redis_queues[0].put = mock.Mock(side_effect=Exception('down'))

        self.pusher.handle_read({'solarNow': 0, 'solarTotal': 0, 'allSolar': {}})

        self.logger.error.assert_called_once()
        self.assertEqual(1, self.pusher.redis_queues[1].qsize())

    def test_name_and_last_run(self):
        self.assertEqual('RedisPusher', self.pusher.get_name())
        self.assertIsNone(self.pusher.seconds_since_last_run_time())
        self.pusher.handle_read({'solarNow': 0, 'solarTotal': 0, 'allSolar': {}})
        self.assertLess(self.pusher.seconds_since_last_run_time(), 5)


if __name__ == '__main__':
    unittest.main()
