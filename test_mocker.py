import threading
import unittest
from unittest import mock

import mocker
from fakes import stop_after


class MockerTests(unittest.TestCase):
    def setUp(self):
        self.stop = threading.Event()
        self.handler = mock.Mock()
        self.mocker = mocker.Mocker(self.stop, mock.Mock(), [self.handler])

    def test_loads_default_message(self):
        self.assertIn('solarNow', self.mocker.default_message)

    def test_missing_default_message_exits(self):
        with mock.patch('builtins.open', side_effect=OSError('missing')), self.assertRaises(SystemExit):
            mocker.Mocker(self.stop, mock.Mock(), [])

    @mock.patch('mocker.random.choice', side_effect=lambda options: options[0])
    @mock.patch('mocker.random.randint', side_effect=lambda low, high: low)
    def test_usage_branch(self, _randint, _choice):
        data = self.mocker.build_mock_data()
        self.assertEqual(1, data['mode'])
        self.assertEqual(0, data['redeliveryNow'])
        self.assertEqual(data['allSolar']['totalEnergy'], data['solarTotal'])
        self.assertTrue(data['created'].endswith('+00:00'))

    @mock.patch('mocker.random.randint', side_effect=lambda low, high: high)
    def test_redelivery_branch(self, _randint):
        data = self.mocker.build_mock_data()
        self.assertEqual(0, data['usageNow'])
        self.assertEqual(4000, data['solarNow'])
        self.assertEqual(4000, data['redeliveryNow'])

    @mock.patch('mocker.time.sleep')
    def test_run_feeds_handlers_until_stopped(self, sleep):
        sleep.side_effect = stop_after(self.stop, calls=2)
        self.mocker.run()
        self.assertEqual(2, self.handler.handle_read.call_count)
        sleep.assert_called_with(10)


if __name__ == '__main__':
    unittest.main()
