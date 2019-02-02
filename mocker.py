from threading import Thread
import copy
import json
import sys
import random
import time
import queue
from threading import Event


class Mocker(Thread):
    def __init__(self, energy_data_queue, stop_event):
        super().__init__()

        self.energy_data_queue = energy_data_queue
        self.stop_event = stop_event
        self.default_message = self.get_default_message()

        self.total_usage = random.randint(1000, 5000)
        self.total_redelivery = random.randint(1000, 5000)
        self.total_solar = random.randint(1000, 5000)
        self.total_gas = random.randint(1000, 5000)

    def get_default_message(self):
        try:
            with open('default_message.json') as default_message_file:
                default_message = json.load(default_message_file)
        except:
            print('Something went wrong when trying to open default_message.json')
            sys.exit()

        return default_message

    def run(self):
        while not self.stop_event.is_set():
            message = self.build_mock_data()
            self.energy_data_queue.put(message)
            time.sleep(10)

    def build_mock_data(self):
        message = copy.deepcopy(self.default_message)
        data = self.generate_mock_data(message)

        return data

    def generate_mock_data(self, message):
        message["mode"] = "1"

        random_decider = random.randint(0,10000)

        if random_decider < 6000:
            usage = random.randint(0, 2500)
            self.total_usage = self.total_usage + int(usage / 100)
            solar = random.randint(0, 2000)
            redelivery = 0
        else:
            usage = 0
            solar = random.randint(0,4000)
            redelivery = random.randint(0, solar)
            self.total_redelivery = self.total_redelivery + int(redelivery / 100)

        self.total_solar = self.total_solar + int(solar / 100)
        self.total_gas = self.total_gas + int(random.randint(0, 110) / 100)

        message['unix_timestamp'] = int(time.time())
        message["usage_now"] = usage
        message["redelivery_now"] = redelivery
        message["solar_now"] = solar
        message["usage_total_high"] = self.total_usage
        message["redelivery_total_high"] = self.total_redelivery
        message["usage_total_low"] = self.total_usage
        message["redelivery_total_low"] = self.total_redelivery
        message["solar_total"] = self.total_solar
        message["usage_gas_now"] = 0
        message["usage_gas_total"] = self.total_gas

        return message

if __name__ == '__main__':
    message_queue = queue.Queue()
    event = Event()
    mocker = Mocker(message_queue, event)
    mocker.start()

    try:
        while(True):
            try:
                data = message_queue.get(False)
                print(data)
            except queue.Empty:
                time.sleep(1)
    except KeyboardInterrupt:
        event.set()
