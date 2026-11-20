import json
import threading
import unittest
from unittest import mock

import requests

import energyportalsender
from fakes import FakeRedisQueue, json_queue, response, stop_after

CONFIG = {'enabled': True, 'api_url': 'https://portal', 'key': 'k', 'name': 'portal', 'max_batch_size': 2}


class SenderTestCase(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch('energyportalsender.RedisQueue', side_effect=lambda name: FakeRedisQueue(name))
        patcher.start()
        self.addCleanup(patcher.stop)
        get = mock.patch('energyportalsender.requests.get')
        post = mock.patch('energyportalsender.requests.post')
        self.get, self.post = get.start(), post.start()
        self.addCleanup(get.stop)
        self.addCleanup(post.stop)
        self.stop = threading.Event()
        self.sender = self.make(CONFIG)

    def make(self, config):
        return energyportalsender.EnergyPortalSender(self.stop, config, mock.Mock())


class SetupTests(SenderTestCase):
    def test_queues_and_url_per_portal(self):
        self.assertEqual('https://portal/api/v3/energy', self.sender.store_energy_url)
        self.assertEqual('queue:normal_portal', self.sender.normal_data_queue.key)
        self.assertEqual('queue:retry_portal', self.sender.retry_data_queue.key)


class QueueTests(SenderTestCase):
    def test_retry_queue_is_read_in_batches(self):
        self.sender.retry_data_queue = json_queue({'n': 1}, {'n': 2}, {'n': 3}, {'n': 4})
        # stops once the batch is larger than max_batch_size
        self.assertEqual([{'n': 1}, {'n': 2}, {'n': 3}], self.sender.read_messages_from_retry_queue())
        self.assertEqual(1, self.sender.retry_data_queue.qsize())

    def test_empty_retry_queue(self):
        self.assertEqual([], self.sender.read_messages_from_retry_queue())

    def test_normal_queue_is_read_in_batches(self):
        self.sender.normal_data_queue = json_queue({'n': 1}, {'n': 2}, {'n': 3}, {'n': 4})
        self.assertEqual([{'n': 1}, {'n': 2}, {'n': 3}], self.sender.read_messages_from_normal_queue())

    def test_retry_storage(self):
        self.sender.store_messages_in_retry_queue([{'n': 1}])
        self.assertEqual([json.dumps({'n': 1})], self.sender.retry_data_queue.items)


class ConnectTests(SenderTestCase):
    def test_ok_connects(self):
        self.get.return_value = response(200)
        self.sender.connect_to_api()
        self.assertTrue(self.sender.connected)

    def test_other_status_does_not_connect(self):
        self.get.return_value = response(502)
        self.sender.connect_to_api()
        self.assertFalse(self.sender.connected)

    def test_unreachable_does_not_connect(self):
        self.get.side_effect = requests.exceptions.ConnectionError()
        self.sender.connected = True
        self.sender.connect_to_api()
        self.assertFalse(self.sender.connected)


class SendTests(SenderTestCase):
    def test_created_is_success(self):
        self.post.return_value = response(201)
        self.sender.send_data_to_api([{'n': 1}])
        args, kwargs = self.post.call_args
        self.assertEqual(('https://portal/api/v3/energy',), args)
        self.assertEqual({'metrics': [{'n': 1}]}, json.loads(kwargs['data']))
        self.assertEqual('k', kwargs['headers']['rpiKey'])
        self.assertTrue(self.sender.retry_data_queue.empty())

    def test_unauthorized_stops_the_sender(self):
        self.post.return_value = response(401)
        self.sender.send_data_to_api([{'n': 1}])
        self.assertTrue(self.stop.is_set())
        self.assertTrue(self.sender.retry_data_queue.empty())

    def test_other_status_is_retried_later(self):
        self.post.return_value = response(500, {'error': 'x'})
        self.sender.send_data_to_api([{'n': 1}])
        self.assertEqual(1, self.sender.retry_data_queue.qsize())

    def test_unreachable_disconnects_and_is_retried_later(self):
        self.post.side_effect = requests.exceptions.ConnectionError()
        self.sender.connected = True
        self.sender.send_data_to_api([{'n': 1}])
        self.assertFalse(self.sender.connected)
        self.assertEqual(1, self.sender.retry_data_queue.qsize())


@mock.patch('energyportalsender.time.sleep')
class RunTests(SenderTestCase):
    def test_disabled_does_nothing(self, _sleep):
        self.make(dict(CONFIG, enabled=False)).run()
        self.get.assert_not_called()

    def test_retry_queue_goes_first(self, sleep):
        self.get.return_value = response(200)
        self.post.return_value = response(201)
        self.sender.retry_data_queue = json_queue({'retry': 1})
        self.sender.normal_data_queue = json_queue({'normal': 1})
        sleep.side_effect = stop_after(self.stop)

        self.sender.run()

        self.assertEqual({'metrics': [{'retry': 1}]}, json.loads(self.post.call_args[1]['data']))
        sleep.assert_called_once_with(5)

    def test_sends_normal_queue_then_idles(self, sleep):
        self.get.return_value = response(200)
        self.post.return_value = response(201)
        self.sender.normal_data_queue = json_queue({'normal': 1})

        def idle(seconds):
            if seconds == 1:  # idle inner loop only ends when the connection drops (it ignores stop_event)
                self.sender.connected = False
                self.stop.set()

        sleep.side_effect = idle

        self.sender.run()

        self.post.assert_called_once()
        self.assertEqual([mock.call(5), mock.call(1), mock.call(5)], sleep.call_args_list)

    def test_not_connected_waits(self, sleep):
        self.get.return_value = response(502)
        sleep.side_effect = stop_after(self.stop)
        self.sender.run()
        self.post.assert_not_called()

    def test_unexpected_error_is_logged_and_loop_continues(self, sleep):
        self.get.side_effect = [ValueError('weird'), response(502)]
        sleep.side_effect = stop_after(self.stop)
        self.sender.run()
        self.sender.logger.error.assert_called_once()
        self.assertEqual(2, self.get.call_count)


if __name__ == '__main__':
    unittest.main()
