from enums import Thread
from enums import Status
from enums import Error
from redis_queue import RedisQueue
import time
import threading
import requests
import json
import logging


class Sender(threading.Thread):
    def __init__(self, status_queue, stop_event, config, logger: logging.Logger):
        super(Sender, self).__init__()

        self.daemon = True
        self.logger = logger

        self.normal_data_queue = RedisQueue('normal')
        self.retry_data_queue = RedisQueue('retry')
        self.status_queue = status_queue
        self.stop_event = stop_event

        self.base_url = config["api_url"]
        self.key = config["key"]
        self.store_energy_url = self.base_url + "/api/v3/energy"
        self.backup_file = "backup"
        self.debug = True if config["debug"] == "true" else False

        self.connected = False

    def run(self):
        self.logger.info('Sender has been started')

        while not self.stop_event.is_set():
            if not self.connected:
                self.connect_to_api()

            while self.connected:
                retry_data = self.read_messages_from_retry_queue()

                if len(retry_data) > 0:
                    self.send_data_to_api(retry_data)
                    break

                normal_data = self.read_messages_from_normal_queue()

                if len(normal_data) > 0:
                    self.send_data_to_api(normal_data)
                    break

                time.sleep(1)

            time.sleep(5)

        self.logger.info('Sender has been terminated')

    def read_messages_from_retry_queue(self):
        retry_data = []

        while not self.retry_data_queue.empty():
            retry_message = self.retry_data_queue.get()
            retry_data.append(json.loads(retry_message.decode('utf-8')))

            if len(retry_data) > 30:
                break

        return retry_data

    def read_messages_from_normal_queue(self):
        normal_data = []

        while not self.normal_data_queue.empty():
            normal_message = self.normal_data_queue.get()
            normal_data.append(json.loads(normal_message.decode('utf-8')))

            if len(normal_data) > 30:
                break

        return normal_data

    def connect_to_api(self):
        try:
            response = requests.get(self.base_url)
            self.connected = response.status_code == requests.codes.ok

            if response.status_code == requests.codes.ok:
                self.connected = True
                self.logger.info('Connected to server running on {}'.format(self.base_url))

        except requests.exceptions.ConnectionError as e:
            self.connected = False
            self.logger.info('Could not connect to the server')

    def send_data_to_api(self, messages):
        headers = {
            'Content-type': 'application/json',
            'Accept': 'application/json',
            'rpiKey': self.key
        }

        try:
            data = {
                "metrics": messages
            }

            response = requests.post(self.store_energy_url, data=json.dumps(data),
                                     headers=headers)

            if response.status_code == requests.codes.created:
                if self.debug:
                    self.logger.info('Successfully stored energy data')
                return

            if response.status_code == requests.codes.unauthorized:
                self.logger.error('Could not authorize with given key')
                self.stop_event.set()
                return

            self.logger.error('Received unexpected status code from server: \'{}\''.format(response.status_code))

            self.store_messages_in_retry_queue(messages)

        except requests.exceptions.ConnectionError as e:
            self.logger.error('Could not reach the server')

            self.connected = False
            self.store_messages_in_retry_queue(messages)

    def store_messages_in_retry_queue(self, messages):
        for message in messages:
            self.retry_data_queue.put(json.dumps(message))
