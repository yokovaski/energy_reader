import logging
from threading import Thread
import copy
import json
import sys
import random
import time

from read_handler_interface import ReadHandlerInterface
from typing import List
import datetime


class Mocker(Thread):
    def __init__(self, stop_event, logger, read_handlers):
        super().__init__()

        self.daemon = True
        self.logger = logger

        self.stop_event = stop_event
        self.default_message = self.get_default_message()
        self.read_handlers = read_handlers
        self.total_usage = random.randint(1000, 5000)
        self.total_redelivery = random.randint(1000, 5000)
        self.total_solar = random.randint(1000, 5000)
        self.total_gas = random.randint(1000, 5000)

    def get_default_message(self):
        try:
            with open('default_message.json') as default_message_file:
                default_message = json.load(default_message_file)
        except:
            self.logger.error('Something went wrong when trying to open default_message.json')
            sys.exit()

        return default_message

    def run(self):
        self.logger.info('Mock reader has been started')

        while not self.stop_event.is_set():
            message = self.build_mock_data()
            self.logger.debug(message)

            for handler in self.read_handlers:
                handler.handle_read(message)

            time.sleep(10)

        self.logger.info('Mock reader has been stopped')

    def build_mock_data(self):
        message = copy.deepcopy(self.default_message)
        energy_data = self.generate_mock_data(message)

        return energy_data

    def generate_mock_data(self, message):
        message["mode"] = 1

        random_decider = random.randint(0, 10000)

        if random_decider < 6000:
            usage = random.randint(0, 2500)
            self.total_usage = self.total_usage + int(usage / 100)
            solar = random.randint(0, 2000)
            redelivery = 0
        else:
            usage = 0
            solar = random.randint(0, 4000)
            redelivery = random.randint(0, solar)
            self.total_redelivery = self.total_redelivery + int(redelivery / 100)

        self.total_gas = self.total_gas + int(random.randint(0, 110) / 100)
        solar_data = self.get_solar(solar)

        message["usageNow"] = usage
        message["redeliveryNow"] = redelivery
        message["solarNow"] = int(solar_data['pac'])
        message["usageTotalHigh"] = self.total_usage
        message["redeliveryTotalHigh"] = self.total_redelivery
        message["usageTotalLow"] = self.total_usage
        message["redeliveryTotalLow"] = self.total_redelivery
        message["solarTotal"] = int(solar_data['totalEnergy'])
        message["usageGasNow"] = 0
        message["usageGasTotal"] = self.total_gas
        message["created"] = datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc).isoformat()
        message['allSolar'] = solar_data

        return message

    def get_solar(self, solar) -> dict:
        self.total_solar = self.total_solar + int(solar / 100)

        solar_data = {
            'dayEnergy': self.total_solar,
            'yearEnergy': self.total_solar,
            'totalEnergy': self.total_solar,
            'pac': solar,
            'udc': int(random.randint(0, 100)),
            'uac': int(random.randint(0, 100)),
            'idc': int(random.randint(0, 100)),
            'iac': int(random.randint(0, 100)),
        }

        return solar_data
