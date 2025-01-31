from redis_queue import RedisQueue
import time
import threading
import requests
import json
import logging


class EnergyPortalSender(threading.Thread):
    def __init__(self, stop_event, config, logger: logging.Logger):
        super(EnergyPortalSender, self).__init__()

        self.daemon = True
        self.logger = logger
        self.stop_event = stop_event

        self.enabled = config["enabled"]
        self.base_url = config["api_url"]
        self.key = config["key"]
        self.name = config["name"]
        self.max_batch_size = config["max_batch_size"]
        self.store_energy_url = self.base_url + "/api/v3/energy"
        self.backup_file = "backup"

        self.normal_data_queue = RedisQueue(f'normal_{self.name}')
        self.retry_data_queue = RedisQueue(f'retry_{self.name}')

        self.connected = False

    def run(self):
        if not self.enabled:
            self.logger.info('Sender is disabled')
            return

        self.logger.info('Sender has been started')

        while not self.stop_event.is_set():
            try:
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
            except Exception as e:
                self.logger.error('Failed to send data', exc_info=e)

        self.logger.info('Sender has been terminated')

    def read_messages_from_retry_queue(self):
        retry_data = []

        while not self.retry_data_queue.empty():
            retry_message = self.retry_data_queue.get()
            retry_data.append(json.loads(retry_message.decode('utf-8')))

            if len(retry_data) > self.max_batch_size:
                break

        if len(retry_data) > 0:
            self.logger.debug(f'{len(retry_data)} message(s) are scheduled for retry.')

        return retry_data

    def read_messages_from_normal_queue(self):
        normal_data = []

        while not self.normal_data_queue.empty():
            normal_message = self.normal_data_queue.get()
            normal_data.append(json.loads(normal_message.decode('utf-8')))

            if len(normal_data) > self.max_batch_size:
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
            self.logger.error('Could not connect to the server')

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

            self.logger.debug(f'{len(messages)} energy message(s) will be send to the api')

            response = requests.post(self.store_energy_url, data=json.dumps(data),
                                     headers=headers)

            if response.status_code == requests.codes.created:
                self.logger.debug('Successfully stored energy data')
                return

            if response.status_code == requests.codes.unauthorized:
                self.logger.error('Could not authorize with given key')
                self.stop_event.set()
                return

            self.logger.error(f'Received unexpected status code \'{response.status_code}\' with response: '
                              f'{response.json()}')

            self.store_messages_in_retry_queue(messages)

        except requests.exceptions.ConnectionError as e:
            self.logger.error('Could not reach the server')

            self.connected = False
            self.store_messages_in_retry_queue(messages)

    def store_messages_in_retry_queue(self, messages):
        self.logger.debug(f'Storing {len(messages)} in de retry queue')

        for message in messages:
            self.retry_data_queue.put(json.dumps(message))
