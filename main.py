#!/usr/bin/env python3
import signal
import sys
from queue import Queue
from mocker import Mocker
from reader import Reader
from sender import Sender
import threading
import json
import logging
import logging.handlers as handlers
import time


formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
info_handler = handlers.TimedRotatingFileHandler('energy_reader.log', when='midnight', interval=1, backupCount=7)
info_handler.setLevel(logging.INFO)
info_handler.setFormatter(formatter)
error_handler = handlers.RotatingFileHandler('error.log', maxBytes=5000, backupCount=3)
error_handler.setLevel(logging.ERROR)
error_handler.setFormatter(formatter)


class MainEnergyReader(threading.Thread):
    def __init__(self):
        super(MainEnergyReader, self).__init__()

        self.daemon = True

        self.logger = logging.getLogger()
        self.logger.setLevel(logging.INFO)
        self.logger.addHandler(info_handler)
        self.logger.addHandler(error_handler)

        self.logger.addHandler(logging.StreamHandler())

        self.message_queue = Queue()
        self.status_queue = Queue()
        self.stop_reader_event = threading.Event()
        self.stop_sender_event = threading.Event()

        self.config = self.load_config()
        self.solar_ip = self.config["solar_ip"]
        self.solar_url = self.config["solar_url"]
        self.base_url = self.config["api_url"]
        self.local = True if self.config["local"] == "true" else False
        self.debug = True if self.config["debug"] == "true" else False
        self.stop = False

        if self.debug:
            stream_handler = logging.StreamHandler()
            stream_handler.setFormatter(formatter)
            self.logger.addHandler(stream_handler)

    @staticmethod
    def load_config():
        with open("config.json") as config_file:
            config = json.load(config_file)

        return config

    def run(self):
        if self.local:
            reader = Mocker(stop_event=self.stop_reader_event, logger=self.logger)
        else:
            reader = Reader(status_queue=self.status_queue, config=self.config, stop_event=self.stop_reader_event,
                            logger=self.logger)

        reader.start()

        sender = Sender(status_queue=self.status_queue, stop_event=self.stop_sender_event, config=self.config,
                        logger=self.logger)

        sender.start()

        while not self.stop:
            time.sleep(0.2)

        self.logger.info('Shutting down...')
        reader.join()
        sender.join()

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
