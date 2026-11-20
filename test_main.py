import json
import logging
import os
import tempfile
import unittest
from unittest import mock

import main

CONFIG = {
    'solar_ip': 'http://192.168.2.35', 'solar_url': '/solar', 'debug': 'false', 'local': 'false',
    'domoticz_url': '', 'domoticz_dummy_name': 'EZ',
    'energy_portals': [{'name': 'EZ', 'enabled': True, 'api_url': 'https://p', 'key': 'k', 'max_batch_size': 20}],
    'mqtt': [{'name': 'HA', 'enabled': True, 'host': 'ha', 'port': 1883, 'username': '', 'password': '',
              'topic': 'energiezicht'}],
}


class MainTestCase(unittest.TestCase):
    def setUp(self):
        # config.json and energy_reader.log live in the working directory
        self.cwd = os.getcwd()
        self.dir = tempfile.TemporaryDirectory()
        os.chdir(self.dir.name)
        self.addCleanup(self.dir.cleanup)
        self.addCleanup(os.chdir, self.cwd)

    def make(self, **overrides):
        with open('config.json', 'w') as f:
            json.dump(dict(CONFIG, **overrides), f)
        energy_reader = main.MainEnergyReader()
        self.addCleanup(self.close_logging, energy_reader)
        return energy_reader

    @staticmethod
    def close_logging(energy_reader):
        for handler in (energy_reader.rotating_file_handler, energy_reader.stream_handler):
            for name in list(logging.Logger.manager.loggerDict):
                logging.getLogger(name).removeHandler(handler)
            handler.close()


class SetupTests(MainTestCase):
    def test_reads_config(self):
        r = self.make()
        self.assertFalse(r.local)
        self.assertFalse(r.debug)
        self.assertFalse(r.push_to_domoticz)
        self.assertTrue(r.push_solar)

    def test_flags(self):
        r = self.make(local='true', debug='true', domoticz_url='http://dz:8080', solar_ip='')
        self.assertTrue(r.local)
        self.assertTrue(r.debug)
        self.assertTrue(r.push_to_domoticz)
        self.assertFalse(r.push_solar)

    def test_valid_uri(self):
        self.assertTrue(main.MainEnergyReader.valid_uri('http://host'))
        self.assertFalse(main.MainEnergyReader.valid_uri('host'))
        self.assertFalse(main.MainEnergyReader.valid_uri(None))
        self.assertFalse(main.MainEnergyReader.valid_uri(123))  # urlparse raises on non-strings

    def test_logger_level_follows_debug(self):
        self.assertEqual(logging.INFO, self.make().create_logger('t-info').level)
        self.assertEqual(logging.DEBUG, self.make(debug='true').create_logger('t-debug').level)

    def test_portal_configs(self):
        self.assertEqual(CONFIG['energy_portals'], self.make().get_energy_portal_configs())

    def test_legacy_single_portal_config(self):
        r = self.make(api_url='https://old', key='k')
        del r.config['energy_portals']
        self.assertEqual([{'name': 'default', 'api_url': 'https://old', 'key': 'k'}], r.get_energy_portal_configs())

    @mock.patch('main.EnergyPortalSender')
    def test_sender_per_portal(self, sender):
        self.assertEqual([sender.return_value], self.make().get_senders(CONFIG['energy_portals']))

    @mock.patch('main.MqttPublisher')
    def test_mqtt_publishers_are_started_and_registered(self, publisher):
        handlers = []
        self.make().register_mqtt_publishers(handlers)
        publisher.return_value.start.assert_called_once()
        self.assertEqual([publisher.return_value], handlers)

    def test_stop_all_threads(self):
        r = self.make()
        r.stop_all_threads()
        self.assertTrue(r.stop)
        self.assertTrue(r.stop_reader_event.is_set())
        self.assertTrue(r.stop_sender_event.is_set())


@mock.patch('main.os._exit')
class ValidateActivityTests(MainTestCase):
    def handler(self, seconds):
        h = mock.Mock()
        h.seconds_since_last_run_time.return_value = seconds
        return h

    def test_not_yet_run_and_recent_are_fine(self, exit_):
        self.make().validate_activity([self.handler(None), self.handler(5)])
        exit_.assert_not_called()

    def test_stalled_handler_crashes_for_restart(self, exit_):
        self.make().validate_activity([self.handler(61)])
        exit_.assert_called_once_with(1)


@mock.patch('main.time.sleep')
@mock.patch('main.EnergyPortalSender')
@mock.patch('main.MqttPublisher')
@mock.patch('main.Mocker')
@mock.patch('main.Reader')
@mock.patch('main.DomoticzPusher')
@mock.patch('main.RedisPusher')
class RunTests(MainTestCase):
    def test_dead_reader_shuts_down(self, redis, domoticz, reader, mocker_, mqtt, sender, _sleep):
        reader.return_value.is_alive.return_value = False
        self.make().run()
        reader.return_value.start.assert_called_once()
        reader.return_value.join.assert_called_once()
        sender.return_value.start.assert_called_once()
        sender.return_value.join.assert_called_once()
        redis.assert_called_once()
        self.assertEqual(['EZ'], redis.call_args[1]['queue_names'])
        mocker_.assert_not_called()
        domoticz.assert_not_called()

    def test_local_mode_uses_mocker(self, redis, domoticz, reader, mocker_, mqtt, sender, _sleep):
        mocker_.return_value.is_alive.return_value = False
        self.make(local='true').run()
        reader.assert_not_called()
        mocker_.return_value.join.assert_called_once()

    def test_dead_domoticz_shuts_down(self, redis, domoticz, reader, mocker_, mqtt, sender, _sleep):
        domoticz.return_value.is_alive.return_value = False
        self.make(domoticz_url='http://dz').run()
        domoticz.return_value.start.assert_called_once()
        domoticz.return_value.join.assert_called_once()

    def test_dead_sender_shuts_down(self, redis, domoticz, reader, mocker_, mqtt, sender, _sleep):
        sender.return_value.is_alive.return_value = False
        self.make().run()
        reader.return_value.join.assert_called_once()

    def test_healthy_loop_checks_activity_until_stopped(self, redis, domoticz, reader, mocker_, mqtt, sender, sleep):
        r = self.make()
        r.validate_activity = mock.Mock()
        sleep.side_effect = lambda _s: setattr(r, 'stop', True)
        r.run()
        r.validate_activity.assert_called_once()
        sleep.assert_called_once_with(1)


if __name__ == '__main__':
    unittest.main()
