import queue
import threading
import unittest
from unittest import mock

import domoticz_pusher
from fakes import FakeRedisQueue, response, stop_after

CONFIG = {'domoticz_url': 'http://dz', 'domoticz_dummy_name': 'EZ'}
OK = response(body={'status': 'OK'})
DATA = {'usageTotalHigh': 1, 'usageTotalLow': 2, 'redeliveryTotalHigh': 3, 'redeliveryTotalLow': 4, 'usageNow': 5,
        'redeliveryNow': 6, 'usageGasTotal': 7, 'solarNow': 8, 'solarTotal': 9_000_000,
        'allSolar': {'iac': 1.5, 'idc': 2.5, 'uac': 230, 'udc': 600, 'dayEnergy': 6454, 'yearEnergy': 4731744,
                     'totalEnergy': 49912700}}


def routes(**by_param):
    """requests.get stand-in answering by a substring of the URL (first match wins)."""
    calls = []

    def get(url):
        calls.append(url)
        for part, answer in by_param.items():
            if part in url:
                return answer
        return OK

    get.calls = calls
    return get


class DomoticzTestCase(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch('domoticz_pusher.RedisQueue', side_effect=lambda name: FakeRedisQueue(name))
        patcher.start()
        self.addCleanup(patcher.stop)
        get = mock.patch('domoticz_pusher.requests.get')
        self.get = get.start()
        self.addCleanup(get.stop)
        self.stop = threading.Event()
        self.pusher = self.make(push_solar=True)

    def make(self, push_solar):
        pusher = domoticz_pusher.DomoticzPusher(CONFIG, self.stop, mock.Mock(), push_solar)
        pusher.queue = queue.Queue()  # multiprocessing.Queue.empty() lags behind put_nowait()
        return pusher

    def value(self, device):
        d = self.pusher.devices[device]
        return d['get_data'](d, DATA)


class DeviceTests(DomoticzTestCase):
    def test_without_solar_only_meter_devices(self):
        self.assertEqual(['electricity', 'gas'], list(self.make(push_solar=False).devices))

    def test_with_solar_all_devices(self):
        self.assertEqual(['electricity', 'gas', 'solar_general', 'solar_iac', 'solar_idc', 'solar_uac', 'solar_udc',
                          'solar_day_total', 'solar_year_total', 'solar_total'], list(self.pusher.devices))
        self.assertEqual('Zonnepanelen (EZ)', self.pusher.devices['solar_general']['name'])

    def test_values(self):
        self.assertEqual('1;2;3;4;5;6', self.value('electricity'))
        self.assertEqual('7', self.value('gas'))
        self.assertEqual('8;9000000', self.value('solar_general'))
        self.assertEqual('1.5', self.value('solar_iac'))
        self.assertEqual('2.5', self.value('solar_idc'))
        self.assertEqual('230', self.value('solar_uac'))
        self.assertEqual('600', self.value('solar_udc'))
        self.assertEqual('6.454', self.value('solar_day_total'))
        self.assertEqual('4731.744', self.value('solar_year_total'))
        self.assertEqual('49.913', self.value('solar_total'))

    def test_change_device_url(self):
        url = self.pusher.devices['solar_general']['change_device_url']('Zon', 12)
        self.assertTrue(url.startswith('/json.htm?type=setused&idx=12&name=Zon'))

    def test_basics(self):
        self.assertEqual('DomoticzPusher', self.pusher.get_name())
        self.assertIsNone(self.pusher.seconds_since_last_run_time())
        self.pusher.last_run = domoticz_pusher.time.time()
        self.assertLess(self.pusher.seconds_since_last_run_time(), 5)
        self.pusher.handle_read({'a': 1})
        self.assertEqual({'a': 1}, self.pusher.queue.get_nowait())

    def test_reset_disconnects_and_forgets_idx(self):
        self.pusher.connected = True
        self.pusher.devices['gas']['idx'] = 5
        self.pusher.reset()
        self.assertFalse(self.pusher.connected)
        self.assertEqual(-1, self.pusher.devices['gas']['idx'])


class QueueValueTests(DomoticzTestCase):
    def test_positive_value_is_remembered(self):
        device = {'queue': FakeRedisQueue()}
        self.assertEqual(10, self.pusher.get_data_with_queue(device, 10))
        self.assertEqual(['10'], [str(i) for i in device['queue'].items])

    def test_zero_falls_back_to_last_known(self):
        device = {'queue': FakeRedisQueue('q', 10)}
        self.assertEqual(10.0, self.pusher.get_data_with_queue(device, 0))
        self.assertEqual(1, device['queue'].qsize())

    def test_zero_without_history_stays_zero(self):
        device = {'queue': FakeRedisQueue()}
        self.assertEqual(0, self.pusher.get_data_with_queue(device, 0))
        self.assertTrue(device['queue'].empty())

    def test_transform_units(self):
        self.assertEqual('1.5', self.pusher.transform({}, 1500, 'KW'))
        self.assertEqual('1.5', self.pusher.transform({}, 1_500_000, 'MW'))
        self.assertEqual('15', self.pusher.transform({}, 15, 'W'))


class PushTests(DomoticzTestCase):
    def test_push(self):
        self.get.return_value = OK
        self.pusher.push_data_to_domoticz(self.pusher.devices['gas'], DATA)
        self.assertEqual('http://dz/json.htm?type=command&param=udevice&idx=-1&nvalue=0&svalue=7',
                         self.get.call_args[0][0])

    def test_http_error_raises(self):
        self.get.return_value = response(500)
        with self.assertRaises(Exception):
            self.pusher.push_data_to_domoticz(self.pusher.devices['gas'], DATA)

    def test_domoticz_error_raises(self):
        self.get.return_value = response(body={'status': 'ERR'})
        with self.assertRaises(Exception):
            self.pusher.push_data_to_domoticz(self.pusher.devices['gas'], DATA)


class FindDevicesTests(DomoticzTestCase):
    def setUp(self):
        super().setUp()
        self.pusher = self.make(push_solar=False)

    def test_finds_idx_by_value_or_idx(self):
        self.get.return_value = response(body={'status': 'OK', 'result': [
            {'name': 'P1 Elektriciteit (EZ)', 'value': 11}, {'name': 'P1 Gas (EZ)', 'idx': 12}]})
        self.assertTrue(self.pusher.try_find_idx_devices())
        self.assertEqual([11, 12], [d['idx'] for d in self.pusher.devices.values()])

    def test_missing_device(self):
        self.get.return_value = response(body={'status': 'OK', 'result': [{'name': 'P1 Gas (EZ)', 'idx': 12}]})
        self.assertFalse(self.pusher.try_find_idx_devices())

    def test_no_result_means_nothing_found(self):
        self.get.return_value = OK
        self.assertFalse(self.pusher.try_find_idx_devices())

    def test_unknown_format_is_logged(self):
        self.get.return_value = response(body={'status': 'OK', 'result': [{'name': 'P1 Elektriciteit (EZ)'}]})
        self.pusher.try_find_idx_devices()
        self.pusher.logger.error.assert_called_once()

    def test_errors_are_logged_but_still_report_found(self):
        # existing behaviour: a failed lookup returns True, so no devices get created
        for answer in (response(500), response(body={'status': 'ERR'})):
            self.get.return_value = answer
            self.assertTrue(self.pusher.try_find_idx_devices())
        self.assertEqual(2, self.pusher.logger.error.call_count)


class StoreHardwareTests(DomoticzTestCase):
    def setUp(self):
        super().setUp()
        self.pusher = self.make(push_solar=False)

    def test_reuses_existing_dummy_hardware(self):
        self.get.side_effect = routes(
            **{'type=hardware': response(body={'status': 'OK', 'result': [
                {'Enabled': 'false', 'Type': 15, 'Name': 'EZ', 'idx': 1},
                {'Enabled': 'true', 'Type': 14, 'Name': 'EZ', 'idx': 2},
                {'Enabled': 'true', 'Type': 15, 'Name': 'Other', 'idx': 3},
                {'Enabled': 'true', 'Type': 15, 'Name': 'EZ', 'idx': 4}]}),
               'createdevice': response(body={'status': 'OK', 'idx': 20})})
        self.pusher.devices['gas']['idx'] = 12

        self.assertTrue(self.pusher.try_store_hardware())

        self.assertEqual(20, self.pusher.devices['electricity']['idx'])
        self.assertEqual(12, self.pusher.devices['gas']['idx'])
        self.assertIn('createdevice&idx=4&', self.get.side_effect.calls[1])
        self.assertEqual(2, len(self.get.side_effect.calls))

    def test_creates_dummy_hardware(self):
        self.get.side_effect = routes(**{'type=hardware': OK, 'addhardware': response(body={'status': 'OK', 'idx': 7}),
                                         'createdevice': response(body={'status': 'OK', 'idx': 20})})
        self.assertTrue(self.pusher.try_store_hardware())
        self.assertIn('createdevice&idx=7&', self.get.side_effect.calls[2])

    def test_failures_return_false(self):
        cases = [
            {'type=hardware': response(500)},
            {'type=hardware': response(body={'status': 'ERR'})},
            {'type=hardware': OK, 'addhardware': response(500)},
            {'type=hardware': OK, 'addhardware': response(body={'status': 'ERR'})},
            {'type=hardware': OK, 'addhardware': response(body={'status': 'OK', 'idx': 7}),
             'createdevice': response(500)},
        ]
        for case in cases:
            with self.subTest(case=list(case)):
                self.pusher.reset()
                self.get.side_effect = routes(**case)
                self.assertFalse(self.pusher.try_store_hardware())


class StoreDeviceTests(DomoticzTestCase):
    def test_creates_device_with_options_and_change_url(self):
        self.get.side_effect = routes(createdevice=response(body={'status': 'OK', 'idx': 20}))
        self.assertEqual(20, self.pusher.try_store_device(4, self.pusher.devices['solar_general']))
        create, change = self.get.side_effect.calls
        self.assertIn('sensorname=Zonnepanelen (EZ)&sensormappedtype=0xF31D', create)
        self.assertIn('type=setused&idx=20', change)

    def test_sensor_options_are_appended(self):
        self.get.side_effect = routes(createdevice=response(body={'status': 'OK', 'idx': 21}))
        self.pusher.try_store_device(4, self.pusher.devices['solar_total'])
        self.assertTrue(self.get.side_effect.calls[0].endswith('&sensoroptions=1;MW'))

    def test_failures_return_none(self):
        created = response(body={'status': 'OK', 'idx': 20})
        cases = [{'createdevice': response(500)}, {'createdevice': response(body={'status': 'ERR'})},
                 {'createdevice': created, 'setused': response(500)},
                 {'createdevice': created, 'setused': response(body={'status': 'ERR'})}]
        for case in cases:
            with self.subTest(case=case):
                self.get.side_effect = routes(**case)
                self.assertIsNone(self.pusher.try_store_device(4, self.pusher.devices['solar_general']))


class ConnectTests(DomoticzTestCase):
    def test_already_connected(self):
        self.pusher.connected = True
        self.assertTrue(self.pusher.is_connected())
        self.get.assert_not_called()

    def test_domoticz_down(self):
        self.get.return_value = response(body={'status': 'ERR'})
        self.assertFalse(self.pusher.is_connected())

    def test_found_devices_connects(self):
        self.get.return_value = OK
        self.pusher.try_find_idx_devices = mock.Mock(return_value=True)
        self.pusher.try_store_hardware = mock.Mock()
        self.assertTrue(self.pusher.is_connected())
        self.assertTrue(self.pusher.connected)
        self.pusher.try_store_hardware.assert_not_called()

    def test_missing_devices_are_created(self):
        self.get.return_value = OK
        self.pusher.try_find_idx_devices = mock.Mock(return_value=False)
        self.pusher.try_store_hardware = mock.Mock(return_value=False)
        # existing behaviour: returns True even when creating failed; retried on the next call
        self.assertTrue(self.pusher.is_connected())
        self.assertFalse(self.pusher.connected)


@mock.patch('domoticz_pusher.time.sleep')
class RunTests(DomoticzTestCase):
    def test_waits_while_queue_is_empty(self, sleep):
        sleep.side_effect = stop_after(self.stop)
        self.pusher.run()
        sleep.assert_called_once_with(1)

    def test_waits_while_not_connected(self, sleep):
        self.pusher.handle_read(DATA)
        self.pusher.is_connected = mock.Mock(return_value=False)
        sleep.side_effect = stop_after(self.stop)
        self.pusher.run()
        sleep.assert_called_once_with(10)

    def test_pushes_every_device(self, sleep):
        self.pusher.handle_read(DATA)
        self.pusher.is_connected = mock.Mock(return_value=True)
        self.pusher.push_data_to_domoticz = mock.Mock()
        sleep.side_effect = stop_after(self.stop)
        self.pusher.run()
        self.assertEqual(10, self.pusher.push_data_to_domoticz.call_count)
        self.assertIsNotNone(self.pusher.last_run)

    def test_push_error_resets(self, sleep):
        self.pusher.handle_read(DATA)
        self.pusher.is_connected = mock.Mock(return_value=True)
        self.pusher.push_data_to_domoticz = mock.Mock(side_effect=Exception('down'))
        self.pusher.reset = mock.Mock()
        sleep.side_effect = stop_after(self.stop)
        self.pusher.run()
        self.pusher.reset.assert_called_once()
        self.pusher.logger.error.assert_called_once()


if __name__ == '__main__':
    unittest.main()
