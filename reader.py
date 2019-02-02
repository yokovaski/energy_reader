import threading
import logging
import time
import requests
from dsmr_parser import telegram_specifications
from dsmr_parser.clients import SerialReader, SERIAL_SETTINGS_V4
from dsmr_parser import obis_references


class Reader(threading.Thread):
    def __init__(self, energy_data_queue, status_queue, config, stop_event):
        super().__init__()

        self.energy_data_queue = energy_data_queue
        self.status_queue = status_queue
        self.reader = self.init_reader()
        self.solar_ip = config['solar_ip']
        self.solar_url = config['solar_url']
        self.stop_event = stop_event

    def init_reader(self):
        serial_reader = SerialReader(
            device="/dev/ttyUSB0",
            serial_settings=SERIAL_SETTINGS_V4,
            telegram_specification=telegram_specifications.V4
        )

        return serial_reader

    def run(self):
        self.read()

    def read(self):
        for telegram in self.reader.read():
            data = self.extract_data_from_telegram(telegram)
            self.energy_data_queue.put(data)
            if self.stop_event.is_set():
                break

        logging.info("Reader has been terminated")

    def extract_data_from_telegram(self, telegram):
        solar = self.read_solar()

        data = {
            'unix_timestamp': int(time.time()),
            'mode': str(telegram[obis_references.ELECTRICITY_ACTIVE_TARIFF].value),
            'usage_now': str(telegram[obis_references.CURRENT_ELECTRICITY_USAGE].value * 1000),
            'redelivery_now': str(telegram[obis_references.CURRENT_ELECTRICITY_DELIVERY].value * 1000),
            'solar_now': solar['now'],
            'usage_total_high': str(telegram[obis_references.ELECTRICITY_USED_TARIFF_2].value * 1000),
            'redelivery_total_high': str(telegram[obis_references.ELECTRICITY_DELIVERED_TARIFF_2].value * 1000),
            'usage_total_low': str(telegram[obis_references.ELECTRICITY_USED_TARIFF_1].value * 1000),
            'redelivery_total_low': str(telegram[obis_references.ELECTRICITY_DELIVERED_TARIFF_1].value * 1000),
            'solar_total': solar['total'],
            'usage_gas_now': "0",
            'usage_gas_total': str(telegram[obis_references.HOURLY_GAS_METER_READING].value * 1000)
        }

        return data

    def read_solar(self):
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
        except Exception:
            return solar
