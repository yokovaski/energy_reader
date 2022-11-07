#!/usr/bin/env python3
import signal
import sys

from domoticz_pusher import DomoticzPusher
from mocker import Mocker
from reader import Reader
from energyportalsender import EnergyPortalSender
import threading
import json
import logging
import logging.handlers as handlers
import time
from urllib.parse import urlparse

from redis_pusher import RedisPusher


class MainEnergyReader(threading.Thread):
    def __init__(self):
        super(MainEnergyReader, self).__init__()

        self.daemon = True

        self.stop_reader_event = threading.Event()
        self.stop_sender_event = threading.Event()

        self.config = self.load_config()
        self.solar_ip = self.config["solar_ip"]
        self.solar_url = self.config["solar_url"]
        self.base_url = self.config["api_url"]
        self.local = True if self.config["local"] == "true" else False
        self.debug = True if self.config["debug"] == "true" else False
        self.push_to_domoticz = True if self.valid_uri(self.config["domoticz_url"]) else False
        self.push_solar = True if self.valid_uri(self.config["solar_ip"]) else False
        self.stop = False

        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        self.rotating_file_handler = handlers.RotatingFileHandler('energy_reader.log', maxBytes=1048576, backupCount=5)
        self.rotating_file_handler.setLevel(logging.DEBUG)
        self.rotating_file_handler.setFormatter(formatter)
        self.stream_handler = logging.StreamHandler()
        self.stream_handler.setLevel(logging.DEBUG)
        self.stream_handler.setFormatter(formatter)

        self.logger = self.create_logger('main')

    @staticmethod
    def load_config():
        with open("config.json") as config_file:
            config = json.load(config_file)

        return config

    def run(self):
        read_handlers = [
            RedisPusher(logger=self.create_logger('RedisPusher')),
        ]

        domoticz_pusher = None

        if self.push_to_domoticz:
            domoticz_pusher = DomoticzPusher(config=self.config, logger=self.create_logger('DomoticzPusher'),
                                             stop_event=self.stop_reader_event, push_solar=self.push_solar)
            domoticz_pusher.start()
            read_handlers.append(domoticz_pusher)

        if self.local:
            reader = Mocker(stop_event=self.stop_reader_event, logger=self.create_logger('Mocker'),
                            read_handlers=read_handlers)
        else:
            reader = Reader(config=self.config, stop_event=self.stop_reader_event, logger=self.create_logger('Reader'),
                            read_handlers=read_handlers)

        reader.start()

        # TODO: don't forget to enable this again
        sender = EnergyPortalSender(stop_event=self.stop_sender_event, config=self.config,
                                    logger=self.create_logger('EnergyPortalSender'))
        sender.start()

        while not self.stop:
            time.sleep(0.2)

        self.logger.info('Shutting down...')
        reader.join()
        sender.join()

        if domoticz_pusher is not None:
            domoticz_pusher.join()

    def stop_all_threads(self):
        self.logger.info('Stopping all threads...')
        self.stop_reader_event.set()
        self.stop_sender_event.set()
        self.stop = True

    @staticmethod
    def valid_uri(x):
        try:
            result = urlparse(x)
            return all([result.scheme, result.netloc])
        except Exception:
            return False

    def create_logger(self, name):
        logger = logging.getLogger(name)

        if self.debug:
            logger.setLevel(logging.DEBUG)
        else:
            logger.setLevel(logging.INFO)

        logger.addHandler(self.rotating_file_handler)
        logger.addHandler(self.stream_handler)

        return logger


if __name__ == '__main__':
    energy_reader = MainEnergyReader()
    energy_reader.start()

    try:
        while True:
            time.sleep(1)
    finally:
        energy_reader.stop_all_threads()
        sys.exit()
