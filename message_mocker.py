from threading import Thread
import json
import sys
import random
import time


class Mocker(Thread):
    def __init__(self, message_queue):
        super().__init__()

        self.raspberry_pi_id = 99
        self.message_queue = message_queue

    def run(self):
        while True:
            message = self.build_mock_data()
            self.message_queue.put(message)
            time.sleep(10)

    def build_mock_data(self):
        try:
            with open('default_message.json') as default_message_file:
                default_message = json.load(default_message_file)
        except:
            print('Something went wrong when trying to open default_message.json')
            sys.exit()

        default_message["raspberry_pi_id"] = self.raspberry_pi_id
        default_message["mode"] = "1"

        message = self.generate_mock_data(default_message)

        return message

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
