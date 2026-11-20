import json
import os
import tempfile
import unittest
from unittest import mock

import extra_solar
from extra_solar import ExtraSolar


def reading(solar_now=1000, solar_total=50_000_000, extra=None):
    data = {'solarNow': solar_now, 'solarTotal': solar_total}
    if extra is not None:
        data['extraSolar'] = extra
    return data


def meter(total, pac=0):
    return {'pac': pac, 'totalEnergy': total}


class ExtraSolarTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.file = os.path.join(self.dir.name, 'state.json')
        self.logger = mock.Mock()
        self.extra = self.make()

    def make(self):
        return ExtraSolar(self.file, self.logger)

    def add(self, extra, **kwargs):
        data = reading(extra=extra, **kwargs)
        self.extra.add_to(data)
        return data

    def stored(self):
        with open(self.file) as f:
            return json.load(f)

    def test_state_file_lives_next_to_the_code(self):
        self.assertEqual(os.path.dirname(os.path.abspath(extra_solar.__file__)), os.path.dirname(extra_solar.STATE_FILE))

    def test_first_reading_sets_baseline_so_total_does_not_jump(self):
        self.assertEqual({'solarNow': 1150, 'solarTotal': 50_000_000}, self.add(meter(149_862, pac=150)))
        self.assertEqual({'baseline': 149_862, 'last_total': 149_862}, self.stored())

    def test_later_readings_add_production_since_baseline(self):
        self.add(meter(149_862))
        self.assertEqual({'solarNow': 1200, 'solarTotal': 50_000_200}, self.add(meter(150_062, pac=200)))
        self.assertEqual({'baseline': 149_862, 'last_total': 150_062}, self.stored())

    def test_restart_while_meter_is_unreachable_keeps_the_total(self):
        self.add(meter(1000))
        self.add(meter(1500))
        self.extra = self.make()
        data = reading()
        data['extraSolar'] = None  # meter unreachable
        self.extra.add_to(data)
        self.assertEqual(50_000_500, data['solarTotal'])

    def test_restart_after_extra_solar_was_switched_off_keeps_the_total(self):
        self.add(meter(1000))
        self.add(meter(1500))
        self.extra = self.make()
        self.assertEqual(50_000_500, self.add(None)['solarTotal'])  # no extraSolar key at all

    def test_unreachable_meter_keeps_last_total(self):
        self.add(meter(1000))
        self.add(meter(1300))
        data = reading()
        data['extraSolar'] = None
        self.extra.add_to(data)
        self.assertEqual({'solarNow': 1000, 'solarTotal': 50_000_300}, data)

    def test_zero_total_is_ignored(self):
        self.add(meter(1000))
        self.add(meter(1300))
        self.assertEqual(50_000_300, self.add(meter(0, pac=50))['solarTotal'])
        self.assertEqual(1300, self.extra.last_total)

    def test_zero_total_before_baseline_does_not_set_it(self):
        self.add(meter(0))
        self.assertIsNone(self.extra.baseline)
        self.assertFalse(os.path.exists(self.file))

    def test_replaced_meter_counts_on_from_where_it_was(self):
        self.add(meter(1000))
        self.add(meter(1300))
        self.assertEqual(50_000_300, self.add(meter(5))['solarTotal'])
        self.logger.warning.assert_called_once()
        self.assertEqual(50_000_310, self.add(meter(15))['solarTotal'])
        self.assertEqual({'baseline': -295, 'last_total': 15}, self.stored())

    def test_failed_fronius_read_keeps_solar_total_zero(self):
        self.add(meter(1000))
        self.assertEqual({'solarNow': 100, 'solarTotal': 0}, self.add(meter(1300, pac=100), solar_now=0, solar_total=0))

    def test_not_configured_leaves_data_untouched(self):
        self.assertEqual({'solarNow': 1000, 'solarTotal': 50_000_000}, self.add(None))
        self.assertFalse(os.path.exists(self.file))

    def test_unchanged_state_is_not_written_again(self):
        self.add(meter(1000))
        with mock.patch('builtins.open') as open_:
            self.add(meter(1000, pac=10))
        open_.assert_not_called()

    def test_missing_file_starts_fresh_silently(self):
        self.assertIsNone(self.extra.baseline)
        self.logger.error.assert_not_called()

    def test_unreadable_file_starts_fresh_and_logs(self):
        with open(self.file, 'w') as f:
            f.write('not json')
        self.assertIsNone(self.make().baseline)
        self.logger.error.assert_called_once()

    def test_failed_save_is_logged_once_and_retried(self):
        with mock.patch('extra_solar.os.replace', side_effect=OSError('read-only')):
            self.add(meter(1000))
            self.add(meter(1100))
        self.logger.error.assert_called_once()
        self.assertEqual(1100, self.extra.last_total)  # still counted in memory

        self.add(meter(1200))
        self.assertEqual({'baseline': 1000, 'last_total': 1200}, self.stored())

        with mock.patch('extra_solar.os.replace', side_effect=OSError('read-only')):
            self.add(meter(1300))
        self.assertEqual(2, self.logger.error.call_count)  # logs again after it had recovered

    def test_no_temp_file_left_behind(self):
        self.add(meter(1000))
        self.assertEqual(['state.json'], os.listdir(self.dir.name))


if __name__ == '__main__':
    unittest.main()
