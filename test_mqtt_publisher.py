import queue
import threading
import unittest
from unittest import mock

import paho.mqtt.client as mqtt

import mqtt_publisher
from fakes import stop_after

CONFIG = {'enabled': True, 'name': 'HA', 'host': 'ha', 'port': 1883, 'username': 'u', 'password': 'p',
          'topic': 'energiezicht'}


class MqttPublisherTestCase(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch('mqtt_publisher.mqtt.Client')
        self.client_class = patcher.start()
        self.addCleanup(patcher.stop)
        self.client = self.client_class.return_value
        self.client.publish.return_value = mock.Mock(rc=mqtt.MQTT_ERR_SUCCESS)
        self.stop = threading.Event()
        self.logger = mock.Mock()
        self.publisher = self.make(CONFIG)

    def make(self, config):
        publisher = mqtt_publisher.MqttPublisher(config, self.stop, self.logger)
        publisher.queue = queue.Queue()  # multiprocessing.Queue.empty() lags behind put_nowait()
        return publisher


class BasicsTests(MqttPublisherTestCase):
    def test_name_and_queue(self):
        self.assertEqual('MqttPublisher HA', self.publisher.get_name())
        self.publisher.handle_read({'a': 1})
        self.assertEqual({'a': 1}, self.publisher.queue.get_nowait())

    def test_extra_solar_is_not_published(self):
        data = {'solarNow': 1, 'extraSolar': {'pac': 2}}
        self.publisher.handle_read(data)
        self.assertEqual({'solarNow': 1}, self.publisher.queue.get_nowait())
        self.assertIn('extraSolar', data)  # the portal path still needs it

    def test_last_run(self):
        self.assertIsNone(self.publisher.seconds_since_last_run_time())
        self.publisher.last_run = mqtt_publisher.time.time() - 3
        self.assertGreaterEqual(self.publisher.seconds_since_last_run_time(), 3)


class PublishTests(MqttPublisherTestCase):
    def published(self):
        return [c[0] for c in self.client.publish.call_args_list]

    def test_nested_dict_becomes_topics_with_typed_values(self):
        self.publisher.publish('energiezicht', 'energiezicht',
                               {'solarNow': 1361, 'created': '2026-11-20', 'allSolar': {'idc': 2.3}})
        self.assertEqual([('energiezicht/solarNow', 1361), ('energiezicht/created', '2026-11-20'),
                          ('energiezicht/allSolar/idc', 2.3)], self.published())

    def test_gas_total_is_published_in_cubic_meters(self):
        self.publisher.publish('energiezicht', 'energiezicht', {'usageGasTotal': 7810123})
        self.assertEqual([('energiezicht/usageGasTotal', 7810.123)], self.published())

    def test_none_is_published_as_text(self):
        self.publisher.publish('t', 't', {'extraSolar': None})
        self.assertEqual([('t/extraSolar', 'None')], self.published())

    def test_failed_publish_raises(self):
        self.client.publish.return_value = mock.Mock(rc=mqtt.MQTT_ERR_NO_CONN)
        with self.assertRaises(Exception):
            self.publisher.publish('t', 't', {'a': 1})

    def test_failed_gas_publish_raises(self):
        self.client.publish.return_value = mock.Mock(rc=mqtt.MQTT_ERR_NO_CONN)
        with self.assertRaises(Exception):
            self.publisher.publish('t', 't', {'usageGasTotal': 1})


class ConnectTests(MqttPublisherTestCase):
    def test_connects_with_credentials(self):
        self.assertTrue(self.publisher.is_connected())
        self.client.username_pw_set.assert_called_once_with('u', 'p')
        self.client.connect.assert_called_once_with('ha', 1883)
        self.client.loop_start.assert_called_once()
        self.assertTrue(self.publisher.connected)

    def test_already_connected_does_not_reconnect(self):
        self.publisher.connected = True
        self.client_class.reset_mock()
        self.assertTrue(self.publisher.is_connected())
        self.client_class.assert_not_called()

    def test_connect_failure_is_logged(self):
        self.client.connect.side_effect = OSError('refused')
        self.assertFalse(self.publisher.is_connected())
        self.logger.error.assert_called_once()


@mock.patch('mqtt_publisher.time')
class RunTests(MqttPublisherTestCase):
    def lose_connection(self, *_args):
        self.stop.set()
        raise Exception('lost')

    def test_disabled_does_nothing(self, time):
        self.make(dict(CONFIG, enabled=False)).run()
        self.client.connect.assert_not_called()

    def test_waits_while_queue_is_empty(self, time):
        time.sleep.side_effect = stop_after(self.stop)
        self.publisher.run()
        time.sleep.assert_called_once_with(1)
        self.client.disconnect.assert_not_called()

    def test_waits_while_not_connected(self, time):
        self.publisher.handle_read({'a': 1})
        self.client.connect.side_effect = OSError('refused')
        time.sleep.side_effect = stop_after(self.stop)
        self.publisher.run()
        time.sleep.assert_called_once_with(5)

    def test_drops_messages_within_ten_seconds_then_publishes(self, time):
        time.time.side_effect = [0, 5, 20, 20]
        self.publisher.handle_read({'old': 1})
        sent = []

        def next_message_after_drop(_seconds):
            if not sent:
                sent.append(True)
                self.publisher.handle_read({'new': 2})
            else:
                self.stop.set()

        # first loop: 5 - 0 < 10, queue drained; then sleep (empty) adds a new message; it is published at t=20
        time.sleep.side_effect = next_message_after_drop
        self.publisher.run()

        self.client.publish.assert_called_once_with('energiezicht/new', 2)
        self.assertEqual(20, self.publisher.last_run)
        self.client.loop_stop.assert_called_once()
        self.client.disconnect.assert_called_once()

    def test_publish_error_disconnects(self, time):
        time.time.side_effect = [0, 20]
        self.publisher.handle_read({'a': 1})
        self.client.publish.side_effect = self.lose_connection
        self.publisher.run()
        self.logger.error.assert_called_once()
        self.assertFalse(self.publisher.connected)
        self.client.disconnect.assert_called_once()

    def test_disconnect_error_is_logged_too(self, time):
        time.time.side_effect = [0, 20]
        self.publisher.handle_read({'a': 1})
        self.client.publish.side_effect = self.lose_connection
        self.client.disconnect.side_effect = Exception('already gone')
        self.publisher.run()
        self.assertEqual(2, self.logger.error.call_count)


if __name__ == '__main__':
    unittest.main()
