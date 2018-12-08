from enums import Thread
from enums import Status
from enums import Error
from queue import Queue
from mocker import Mocker
from reader import Reader
from sender import Sender
import threading
import json
import time


class MainEnergyReader(threading.Thread):
    def __init__(self):
        super(MainEnergyReader, self).__init__()
        self.message_queue = Queue()
        self.status_queue = Queue()
        self.stop_reader_event = threading.Event()
        self.stop_sender_event = threading.Event()

        config = self.load_config()
        self.solar_ip = config["solar_ip"]
        self.solar_url = config["solar_url"]
        self.base_url = config["api_url"]
        self.local = config["local"]
        self.raspberry_pi_id = config["raspberry_pi_id"]

    def load_config(self):
        with open("config.json") as config_file:
            config = json.load(config_file)

        return config

    def run(self):
        if self.local == "true":
            reader = Mocker(self.raspberry_pi_id, self.message_queue, self.stop_reader_event)
        else:
            reader = Reader(self.raspberry_pi_id, self.message_queue, self.status_queue, self.stop_reader_event)

        reader.start()

        sender = Sender(self.message_queue, self.status_queue, self.stop_sender_event)
        sender.start()

        while True:
            while not self.status_queue.empty():
                self.handle_status_message_of_thread(self.status_queue.get())

            time.sleep(1)

    def handle_status_message_of_thread(self, message):
        print(message["thread"] + " | " + message)
        if message["thread"] is Thread.SENDER:
            do_stuff = ""


if __name__ == '__main__':
    energy_reader = MainEnergyReader()
    energy_reader.start()
