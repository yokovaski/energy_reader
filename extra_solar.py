import json
import logging
import os

# Next to the code, so it does not depend on the working directory
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'extra_solar_state.json')


class ExtraSolar:
    """
    Adds a second solar system (read by Reader into data['extraSolar']) to solarNow/solarTotal.
    Only used on the way to the energy portal: MQTT and Domoticz keep the Fronius-only values,
    because Home Assistant already reads the second system itself.

    The second system's lifetime total is counted from a baseline taken the first time it is seen,
    so the portal's solarTotal does not jump when this is switched on. Baseline and last total are
    stored on disk, so a restart while the meter is unreachable does not make solarTotal go down.
    """

    def __init__(self, state_file: str, logger: logging.Logger):
        self.state_file = state_file
        self.logger = logger
        self.baseline, self.last_total = self._load()
        self.saved = (self.baseline, self.last_total)
        self.save_failing = False

    def _load(self):
        try:
            with open(self.state_file) as f:
                state = json.load(f)
            return int(state['baseline']), int(state['last_total'])
        except FileNotFoundError:
            return None, None
        except (OSError, ValueError, KeyError, TypeError) as e:
            self.logger.error(f'Could not read {self.state_file}, extra solar starts counting from zero', exc_info=e)
            return None, None

    def _save(self):
        state = (self.baseline, self.last_total)
        if state == self.saved:
            return

        try:
            # Write and rename, so a crash mid-write never leaves a half file behind
            tmp = self.state_file + '.tmp'
            with open(tmp, 'w') as f:
                json.dump({'baseline': self.baseline, 'last_total': self.last_total}, f)
            os.replace(tmp, self.state_file)
            self.saved = state
            self.save_failing = False
        except OSError as e:
            if not self.save_failing:
                self.logger.error(f'Could not store extra solar state in {self.state_file}, will retry', exc_info=e)
            self.save_failing = True

    def add_to(self, data: dict) -> None:
        extra = data.pop('extraSolar', None)

        if extra is not None:
            total = extra['totalEnergy']

            # A 0 total is a meter glitch or a brand-new meter; wait for a real reading
            if total > 0:
                if self.baseline is None:
                    self.baseline = self.last_total = total
                elif total < self.last_total:
                    self.logger.warning(f'Extra solar meter total went down ({self.last_total} -> {total} Wh), '
                                        f'assuming a replaced meter and counting on from here')
                    self.baseline -= self.last_total - total  # keeps what was counted so far

                self.last_total = total

            self._save()
            data['solarNow'] += extra['pac']

        # solarTotal 0 means the Fronius could not be read; the portal skips zeros, so keep it 0
        if data['solarTotal'] > 0 and self.baseline is not None:
            data['solarTotal'] += self.last_total - self.baseline
