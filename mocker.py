from threading import Thread
import copy
import json
import sys
import random
import time


class Mocker(Thread):
    def __init__(self, raspberry_pi_id, energy_data_queue, stop_event):
        super().__init__()

        self.raspberry_pi_id = raspberry_pi_id
        self.energy_data_queue = energy_data_queue
        self.stop_event = stop_event
        self.default_message = self.get_default_message()

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

        message["raspberry_pi_id"] = self.raspberry_pi_id
        message["mode"] = "1"

        data = self.generate_mock_data(message)

        return data

    def generate_mock_data(self, message):
        message["usage_now"] = random.randint(0,2500)
        message["redelivery_now"] = random.randint(0,3000)
        message["solar_now"] = random.randint(0,3000)
        message["usage_total_high"] = random.randint(0,3000)
        message["redelivery_total_high"] = random.randint(0,3000)
        message["usage_total_low"] = random.randint(0,3000)
        message["redelivery_total_low"] = random.randint(0,3000)
        message["solar_total"] = random.randint(0,3000)
        message["usage_gas_now"] = random.randint(0,3000)
        message["usage_gas_total"] = random.randint(0,3000)

        return message
