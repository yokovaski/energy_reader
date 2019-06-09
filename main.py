#!/usr/bin/env python3

from enums import Thread
from enums import Status
from enums import Error
from queue import Queue
from mocker import Mocker
from reader import Reader
from sender import Sender
from _datetime import datetime
import threading
import json
import time
import sys


class MainEnergyReader(threading.Thread):
    def __init__(self):
        super(MainEnergyReader, self).__init__()
        self.message_queue = Queue()
        self.status_queue = Queue()
        self.stop_reader_event = threading.Event()
        self.stop_sender_event = threading.Event()

        self.config = self.load_config()
        self.solar_ip = self.config["solar_ip"]
        self.solar_url = self.config["solar_url"]
        self.base_url = self.config["api_url"]
        self.local = True if self.config["local"] == "true" else False
        self.console_mode = True if self.config["console_mode"] == "true" else False
        self.stop = False

    def load_config(self):
        with open("config.json") as config_file:
            config = json.load(config_file)

        return config

    def run(self):
        if self.local:
            reader = Mocker(stop_event=self.stop_reader_event)
        else:
            reader = Reader(status_queue=self.status_queue, config=self.config,
                            stop_event=self.stop_reader_event)

        reader.start()

        sender = Sender(status_queue=self.status_queue,
                        stop_event=self.stop_sender_event, config=self.config)

        sender.start()

        while not self.stop:
            while not self.status_queue.empty():
                self.handle_status_message_of_thread(self.status_queue.get())

            time.sleep(1)

        self.handle_status_message_of_thread('[MAIN] | Reading last messages from children before shutting down...')

        # Handle messages that are still in the queue
        while not self.status_queue.empty():
            self.handle_status_message_of_thread(self.status_queue.get())

        self.handle_status_message_of_thread('[MAIN] | Shutting down...')

    def handle_status_message_of_thread(self, message):
        log_message = '(UTC) {} | {}'.format(datetime.utcnow(), message)

        if self.console_mode:
            print(log_message)
        else:
            file = open('energy_reader.log', 'a')
            file.write(log_message + "\n")
            file.close()

    def stop_all_threads(self):
        self.handle_status_message_of_thread('[MAIN] | Stopping all threads...')
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
