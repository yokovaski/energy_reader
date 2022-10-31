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
        self.stop = False

        self.logger = logging.getLogger()

        if self.debug:
            self.logger.setLevel(logging.DEBUG)
        else:
            self.logger.setLevel(logging.INFO)

        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler = handlers.RotatingFileHandler('energy_reader.log', maxBytes=1048576, backupCount=5)
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)

        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        self.logger.addHandler(stream_handler)

    @staticmethod
    def load_config():
        with open("config.json") as config_file:
            config = json.load(config_file)

        return config

    def run(self):
        domoticz_pusher = DomoticzPusher(config=self.config, logger=self.logger, stop_event=self.stop_reader_event)
        domoticz_pusher.start()

        read_handlers = [
            # RedisPusher(logger=self.logger),
            domoticz_pusher
        ]

        if self.local:
            reader = Mocker(stop_event=self.stop_reader_event, logger=self.logger, read_handlers=read_handlers)
        else:
            reader = Reader(config=self.config, stop_event=self.stop_reader_event, logger=self.logger,
                            read_handlers=read_handlers)

        reader.start()

        # TODO: don't forget to enable this again
        sender = EnergyPortalSender(stop_event=self.stop_sender_event, config=self.config, logger=self.logger)
        # sender.start()

        while not self.stop:
            time.sleep(0.2)

        self.logger.info('Shutting down...')
        reader.join()
        # sender.join()

    def stop_all_threads(self):
        self.logger.info('Stopping all threads...')
        self.stop_reader_event.set()
        self.stop_sender_event.set()
        self.stop = True


if __name__ == '__main__':
    energy_reader = MainEnergyReader()
    energy_reader.start()

    try:
        while True:
            time.sleep(1)
    finally:
        energy_reader.stop_all_threads()
        sys.exit()
