from enums import Thread
from enums import Status
from enums import Error
import time
import threading
import queue
import logging
import requests


class Sender(threading.Thread):
    def __init__(self, energy_data_queue, status_queue, stop_event, config):
        super(Sender, self).__init__()

        self.energy_data_queue = energy_data_queue
        self.status_queue = status_queue
        self.stop_event = stop_event

        self.base_url = config["api_url"]
        self.key = config["key"]
        self.store_energy_url = self.base_url + "/v2/energy"
        self.backup_file = "backup"

    def run(self):
        logging.info("Sender has been started")

        while not self.stop_event.is_set():
            try:
                data = self.energy_data_queue.get(False)
                self.send_data_to_api(data)
            except queue.Empty:
                time.sleep(1)

        logging.info("Sender has been terminated")

    def send_data_to_api(self, messages):
        headers = {
            'Content-type': 'application/json',
            'Accept': 'application/json'
        }

        try:
            response = requests.post(self.store_energy_url, data=json.dumps({'data': messages, "token": self.key}),
                                     headers=headers)

            if response.status_code == requests.codes.created:
                return

            if response.status_code == requests.codes.unauthorized:
                self.send_message_to_listeners(Status.STOPPED, Error.UNAUTHORIZED,
                                               "Could not authorize with given key")
                self.stop_event.set()

        except requests.exceptions.ConnectionError:
            self.send_message_to_listeners(Status.RUNNING, Error.SERVER_UNREACHABLE, "Could not reach the server")
            # self.previous_request_failed = True
            # self.buffer_backup_data(data)
            # TODO write data to backup

    def write_messages_to_backup_file(self, messages):
        with open(self.backup_file) as backup_file:
            do_something = ""

    def send_message_to_listeners(self, status, error=None, message=None):
        message = dict()
        message["thread"] = Thread.SENDER
        message["status"] = status

        if error is not None:
            message["error"] = error

        if message is not None:
            message["message"] = message

        self.status_queue.put(message)
