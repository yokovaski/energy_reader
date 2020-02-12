import datetime
import threading
from enums import Thread, Status, Error
import time
import requests
import json
from dsmr_parser import telegram_specifications
from dsmr_parser.clients import SerialReader, SERIAL_SETTINGS_V4
from dsmr_parser import obis_references
from redis_queue import RedisQueue


class Reader(threading.Thread):
    def __init__(self, status_queue, config, stop_event):
        super().__init__()

        self.energy_data_queue = RedisQueue('normal')
        self.status_queue = status_queue
        self.reader = self.init_reader()
        self.solar_ip = config['solar_ip']
        self.solar_url = self.solar_ip + config['solar_url']
        self.stop_event = stop_event
        self.console_mode = True if config["console_mode"] == "true" else False

    def init_reader(self):
        serial_reader = SerialReader(
            device="/dev/ttyUSB0",
            serial_settings=SERIAL_SETTINGS_V4,
            telegram_specification=telegram_specifications.V4
        )

        return serial_reader

    def run(self):
        self.send_message_to_listeners(Status.RUNNING, description='Reader has been started')
        self.read()

    def read(self):
        for telegram in self.reader.read():
            energy_data = self.extract_data_from_telegram(telegram)

            if self.console_mode:
                self.send_message_to_listeners(Status.RUNNING, description=energy_data)

            self.energy_data_queue.put(json.dumps(energy_data))

            if self.stop_event.is_set():
                break

        self.send_message_to_listeners(Status.STOPPED, description='Reader has been stopped')

    def extract_data_from_telegram(self, telegram):
        solar = self.read_solar()

        data = {
            'mode': telegram[obis_references.ELECTRICITY_ACTIVE_TARIFF].value,
            'usageNow': int(telegram[obis_references.CURRENT_ELECTRICITY_USAGE].value * 1000),
            'redeliveryNow': int(telegram[obis_references.CURRENT_ELECTRICITY_DELIVERY].value * 1000),
            'solarNow': solar['now'],
            'usageTotalHigh': int(telegram[obis_references.ELECTRICITY_USED_TARIFF_2].value * 1000),
            'redeliveryTotalHigh': int(telegram[obis_references.ELECTRICITY_DELIVERED_TARIFF_2].value * 1000),
            'usageTotalLow': int(telegram[obis_references.ELECTRICITY_USED_TARIFF_1].value * 1000),
            'redeliveryTotalLow': int(telegram[obis_references.ELECTRICITY_DELIVERED_TARIFF_1].value * 1000),
            'solarTotal': solar['total'],
            'usageGasNow': 0,
            'usageGasTotal': int(telegram[obis_references.HOURLY_GAS_METER_READING].value * 1000),
            'created': datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc).isoformat()
        }

        return data

    def read_solar(self, retry=False):
        solar = {
            "now": 0,
            "total": 0
        }

        if str(self.solar_ip) is "":
            return solar

        try:
            time.sleep(0.85)
            solar_data = requests.get(url=self.solar_url, timeout=2).json()
            solar['now'] = solar_data['Body']['Data']['PAC']['Value']
            solar['total'] = solar_data['Body']['Data']['TOTAL_ENERGY']['Value']

            return solar
        except requests.exceptions.ConnectTimeout:
            return solar
        except Exception:
            if not retry:
                solar = self.read_solar(True)

            self.send_message_to_listeners(Status.RUNNING, Error.SOLAR_API, 'Could not read data from solar api: {}'.format(self.solar_url))

            return solar

    def send_message_to_listeners(self, status, error=None, description=None):
        message = dict()
        message["thread"] = Thread.READER
        message["status"] = status

        if error is not None:
            message["error"] = error

        if message is not None:
            message["description"] = description

        self.status_queue.put(message)
