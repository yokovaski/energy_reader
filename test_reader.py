import threading
import unittest
from decimal import Decimal
from types import SimpleNamespace
from unittest import mock

import requests
from dsmr_parser import obis_references as obis

import reader
from fakes import response

CONFIG = {'solar_ip': 'http://fronius', 'solar_url': '/solar', 'debug': 'false'}

TELEGRAM = {
    obis.ELECTRICITY_ACTIVE_TARIFF: SimpleNamespace(value=Decimal('0002')),
    obis.CURRENT_ELECTRICITY_USAGE: SimpleNamespace(value=Decimal('0.250')),
    obis.CURRENT_ELECTRICITY_DELIVERY: SimpleNamespace(value=Decimal('1.355')),
    obis.ELECTRICITY_USED_TARIFF_2: SimpleNamespace(value=Decimal('20128.540')),
    obis.ELECTRICITY_DELIVERED_TARIFF_2: SimpleNamespace(value=Decimal('26291.791')),
    obis.ELECTRICITY_USED_TARIFF_1: SimpleNamespace(value=Decimal('22965.116')),
    obis.ELECTRICITY_DELIVERED_TARIFF_1: SimpleNamespace(value=Decimal('11660.628')),
    obis.HOURLY_GAS_METER_READING: SimpleNamespace(value=Decimal('7810.123')),
}

FRONIUS = {'Body': {'Data': {
    'DAY_ENERGY': {'Value': 6454}, 'YEAR_ENERGY': {'Value': 4731744}, 'TOTAL_ENERGY': {'Value': 49912700},
    'PAC': {'Value': 2145}, 'UDC': {'Value': 687}, 'UAC': {'Value': 233}, 'IDC': {'Value': 2.3}, 'IAC': {'Value': 9.1},
}}}


def make_reader(config=None, handlers=()):
    with mock.patch('reader.SerialReader') as serial, mock.patch('reader.RedisQueue'):
        r = reader.Reader(dict(CONFIG, **(config or {})), threading.Event(), mock.Mock(), list(handlers))
    r.serial = serial
    return r


class ReaderSetupTests(unittest.TestCase):
    def test_init_builds_serial_reader_and_config(self):
        r = make_reader({'debug': 'true'})
        r.serial.assert_called_once()
        self.assertEqual('http://fronius/solar', r.solar_url)
        self.assertEqual('', r.extra_solar_url)
        self.assertTrue(r.debug)
        self.assertTrue(r.daemon)

    def test_run_starts_reading(self):
        r = make_reader()
        r.read = mock.Mock()
        r.run()
        r.read.assert_called_once()


class ExtractTests(unittest.TestCase):
    def test_converts_telegram_to_watts_and_watt_hours(self):
        r = make_reader()
        r.read_solar = mock.Mock(return_value={'pac': 2145, 'totalEnergy': 49912700})

        data = r.extract_data_from_telegram(TELEGRAM)

        self.assertEqual(2, data['mode'])
        self.assertEqual(250, data['usageNow'])
        self.assertEqual(1355, data['redeliveryNow'])
        self.assertEqual(2145, data['solarNow'])
        self.assertEqual(20128540, data['usageTotalHigh'])
        self.assertEqual(26291791, data['redeliveryTotalHigh'])
        self.assertEqual(22965116, data['usageTotalLow'])
        self.assertEqual(11660628, data['redeliveryTotalLow'])
        self.assertEqual(49912700, data['solarTotal'])
        self.assertEqual(0, data['usageGasNow'])
        self.assertEqual(7810123, data['usageGasTotal'])
        self.assertTrue(data['created'].endswith('+00:00'))
        self.assertNotIn('extraSolar', data)

    def test_adds_extra_solar_when_configured(self):
        r = make_reader({'extra_solar_url': 'http://kwh/api/v1/data'})
        r.read_solar = mock.Mock(return_value={'pac': 0, 'totalEnergy': 0})
        r.read_extra_solar = mock.Mock(return_value={'pac': 150, 'totalEnergy': 149862})

        self.assertEqual({'pac': 150, 'totalEnergy': 149862}, r.extract_data_from_telegram(TELEGRAM)['extraSolar'])


@mock.patch('reader.time.sleep')
@mock.patch('reader.requests.get')
class ReadSolarTests(unittest.TestCase):
    def test_no_solar_ip_returns_zeros_without_request(self, get, _sleep):
        r = make_reader({'solar_ip': ''})
        self.assertEqual(0, r.read_solar()['pac'])
        get.assert_not_called()

    def test_reads_all_values(self, get, _sleep):
        get.return_value = response(body=FRONIUS)
        solar = make_reader().read_solar()
        self.assertEqual({'pac': 2145, 'dayEnergy': 6454, 'yearEnergy': 4731744, 'totalEnergy': 49912700,
                          'udc': 687, 'uac': 233, 'idc': 2.3, 'iac': 9.1}, solar)
        get.assert_called_once_with(url='http://fronius/solar', timeout=2)

    def test_without_pac_at_night_only_energy_is_filled(self, get, _sleep):
        data = {k: v for k, v in FRONIUS['Body']['Data'].items() if k in ('DAY_ENERGY', 'YEAR_ENERGY', 'TOTAL_ENERGY')}
        get.return_value = response(body={'Body': {'Data': data}})
        solar = make_reader().read_solar()
        self.assertEqual(0, solar['pac'])
        self.assertEqual(49912700, solar['totalEnergy'])

    def test_connect_timeout_returns_zeros(self, get, _sleep):
        get.side_effect = requests.exceptions.ConnectTimeout()
        self.assertEqual(0, make_reader().read_solar()['totalEnergy'])
        get.assert_called_once()

    def test_other_error_is_retried_once(self, get, _sleep):
        get.side_effect = [ValueError('bad json'), response(body=FRONIUS)]
        self.assertEqual(2145, make_reader().read_solar()['pac'])

    def test_second_failure_is_logged(self, get, _sleep):
        get.side_effect = ValueError('bad json')
        r = make_reader()
        self.assertEqual(0, r.read_solar()['pac'])
        self.assertEqual(2, get.call_count)
        r.logger.error.assert_called_once()


@mock.patch('reader.requests.get')
class ReadExtraSolarTests(unittest.TestCase):
    def setUp(self):
        self.reader = make_reader({'extra_solar_url': 'http://kwh/api/v1/data'})

    def test_production_is_negative_power_on_the_meter(self, get):
        get.return_value = response(body={'active_power_w': -169.548, 'total_power_export_kwh': 149.8626})
        self.assertEqual({'pac': 170, 'totalEnergy': 149863}, self.reader.read_extra_solar())
        get.assert_called_once_with(url='http://kwh/api/v1/data', timeout=1)

    def test_consumption_at_night_counts_as_zero_production(self, get):
        get.return_value = response(body={'active_power_w': 1.2, 'total_power_export_kwh': 149.0})
        self.assertEqual(0, self.reader.read_extra_solar()['pac'])

    def test_failure_returns_none_and_warns(self, get):
        get.side_effect = requests.exceptions.ConnectionError()
        self.assertIsNone(self.reader.read_extra_solar())
        self.reader.logger.warning.assert_called_once()

    def test_only_state_changes_are_logged(self, get):
        ok = response(body={'active_power_w': -10, 'total_power_export_kwh': 1})
        get.side_effect = [requests.exceptions.ConnectionError(), requests.exceptions.ConnectionError(), ok, ok]
        for _ in range(4):
            self.reader.read_extra_solar()
        self.reader.logger.warning.assert_called_once()
        self.reader.logger.info.assert_called_once()


@mock.patch('reader.time.time')
class ReadLoopTests(unittest.TestCase):
    def setUp(self):
        self.good = mock.Mock()
        self.bad = mock.Mock()
        self.bad.get_name.return_value = 'Bad'
        self.bad.handle_read.side_effect = Exception('boom')
        self.reader = make_reader(handlers=[self.bad, self.good])
        self.reader.extract_data_from_telegram = mock.Mock(side_effect=lambda t: {'t': t})

    def test_only_every_ten_seconds_and_handler_errors_are_contained(self, now):
        self.reader.reader.read.return_value = iter(['t1', 't2', 't3'])
        now.side_effect = [100.0, 105.0, 110.0]

        self.reader.read()

        self.assertEqual([mock.call({'t': 't1'}), mock.call({'t': 't3'})], self.good.handle_read.call_args_list)
        self.assertEqual(2, self.reader.logger.error.call_count)

    def test_stops_when_stop_event_is_set(self, now):
        self.reader.reader.read.return_value = iter(['t1', 't2'])
        now.side_effect = [100.0, 200.0]
        self.reader.stop_event.set()

        self.reader.read()

        self.good.handle_read.assert_called_once_with({'t': 't1'})


if __name__ == '__main__':
    unittest.main()
