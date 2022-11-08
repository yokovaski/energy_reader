import datetime
import logging
import threading
import time
import requests
from dsmr_parser import telegram_specifications
from dsmr_parser.clients import SerialReader, SERIAL_SETTINGS_V4
from dsmr_parser import obis_references
from typing import List

from read_handler_interface import ReadHandlerInterface
from redis_queue import RedisQueue


class Reader(threading.Thread):
    def __init__(self, config: dict, stop_event: threading.Event, logger: logging.Logger,
                 read_handlers: List[ReadHandlerInterface]):
        super().__init__()

        self.daemon = True
        self.logger: logging.Logger = logger
        self.read_handlers: List[ReadHandlerInterface] = read_handlers

        self.energy_data_queue = RedisQueue('normal')
        self.reader = self.init_reader()
        self.solar_ip = config['solar_ip']
        self.solar_url = self.solar_ip + config['solar_url']
        self.stop_event = stop_event
        self.debug = True if config["debug"] == "true" else False

    @staticmethod
    def init_reader():
        serial_reader = SerialReader(
            device="/dev/ttyUSB0",
            serial_settings=SERIAL_SETTINGS_V4,
            telegram_specification=telegram_specifications.V4
        )

        return serial_reader

    def run(self):
        self.logger.info('Reader has been started')
        self.read()

    def read(self):
        for telegram in self.reader.read():
            energy_data = self.extract_data_from_telegram(telegram)
            self.logger.debug(energy_data)

            for read_handler in self.read_handlers:
                name: str = 'Unknown'

                try:
                    name = read_handler.get_name()
                    read_handler.handle_read(energy_data)
                except Exception:
                    self.logger.error(f'Failed to push data to read handler {name}')

            if self.stop_event.is_set():
                break

        self.logger.info('Reader has been stopped')

    def extract_data_from_telegram(self, telegram):
        solar = self.read_solar()

        data = {
            'mode': int(telegram[obis_references.ELECTRICITY_ACTIVE_TARIFF].value),
            'usageNow': int(telegram[obis_references.CURRENT_ELECTRICITY_USAGE].value * 1000),
            'redeliveryNow': int(telegram[obis_references.CURRENT_ELECTRICITY_DELIVERY].value * 1000),
            'solarNow': int(solar['pac']),
            'usageTotalHigh': int(telegram[obis_references.ELECTRICITY_USED_TARIFF_2].value * 1000),
            'redeliveryTotalHigh': int(telegram[obis_references.ELECTRICITY_DELIVERED_TARIFF_2].value * 1000),
            'usageTotalLow': int(telegram[obis_references.ELECTRICITY_USED_TARIFF_1].value * 1000),
            'redeliveryTotalLow': int(telegram[obis_references.ELECTRICITY_DELIVERED_TARIFF_1].value * 1000),
            'solarTotal': int(solar['totalEnergy']),
            'usageGasNow': 0,
            'usageGasTotal': int(telegram[obis_references.HOURLY_GAS_METER_READING].value * 1000),
            'created': datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc).isoformat(),
            'allSolar': solar
        }

        return data

    def read_solar(self, retry=False):
        solar = {
            'pac': 0,
            'totalEnergy': 0,
            'udc': 0,
            'uac': 0,
            'idc': 0,
            'iac': 0,
        }

        if str(self.solar_ip) == "":
            return solar

        try:
            time.sleep(0.85)
            solar_data = requests.get(url=self.solar_url, timeout=2).json()['Body']['Data']
            solar['dayEnergy'] = solar_data['YEAR_ENERGY']['Value']
            solar['yearEnergy'] = solar_data['DAY_ENERGY']['Value']
            solar['totalEnergy'] = solar_data['TOTAL_ENERGY']['Value']

            if 'PAC' not in solar_data:
                return solar

            solar['pac'] = solar_data['PAC']['Value']
            solar['udc'] = solar_data['UDC']['Value']
            solar['uac'] = solar_data['UAC']['Value']
            solar['idc'] = solar_data['IDC']['Value']
            solar['iac'] = solar_data['IAC']['Value']

            return solar
        except requests.exceptions.ConnectTimeout:
            return solar
        except Exception as e:
            if not retry:
                solar = self.read_solar(True)
            else:
                self.logger.error('Could not read data from solar api: {}'.format(self.solar_url), exc_info=e)

            return solar
