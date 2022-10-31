import json
import logging
from threading import Thread
import threading
import time
from queue import Queue

import requests

from read_handler_interface import ReadHandlerInterface

# solar idx
# /json.htm?type=command&param=udevice&idx=<idx>&nvalue=<numeric value>&svalue=<string value>&parsetrigger=<false/true>

# p1 smart meter

# electricity should be posted in W(h)
# /json.htm?type=command&param=udevice&idx=IDX&nvalue=0&svalue=usageTotalHigh;usageTotalLow;redeliveryTotalHigh;redeliveryTotalLow;usageNow;redeliveryNow

# gas total in liter (I.E. 16.093 m3 should be posted as 16093)
# /json.htm?type=command&param=udevice&idx=IDX&nvalue=0&svalue=usageGasTotal


class DomoticzPusher(Thread, ReadHandlerInterface):
    def __init__(self, config: dict, stop_event: threading.Event, logger: logging.Logger):
        super().__init__()
        
        self.queue: Queue = Queue()
        self.stop_event = stop_event
        self.logger = logger
        self.connected = False
        self.domoticz_url = config['domoticz_url']

        self.electricity_device_name = 'p1Electricity'
        self.electricity_device_idx = -1
        self.gas_device_name = 'p1Gas'
        self.gas_device_idx = -1

    def handle_read(self, data: dict) -> None:
        self.queue.put_nowait(data)

    def get_name(self) -> str:
        return 'DomoticzPusher'

    def run(self):
        while not self.stop_event.is_set():
            if not self.connected:
                response = requests.get(f'{self.domoticz_url}/json.htm?type=command&param=getversion')
                response_data = response.json()

                if response.ok and response_data['status'] == 'OK':
                    self.find_idx_devices()
                    self.connected = True
                else:
                    time.sleep(10)
                    continue

            if self.queue.empty():
                time.sleep(1)

            try:
                print('')
                data: dict = self.queue.get_nowait()

                response = requests.get(f'{self.domoticz_url}/json.htm?type=command&param=udevice&idx={self.electricity_device_idx}&nvalue=0&svalue={data["usageTotalHigh"]};{data["usageTotalLow"]};{data["redeliveryTotalHigh"]};{data["redeliveryTotalLow"]};{data["usageNow"]};{data["redeliveryNow"]}')
                response_json = response.json()

                if response_json['status'] != 'OK':
                    raise Exception("Failed to push electricity")

                response = requests.get(f'{self.domoticz_url}/json.htm?type=command&param=udevice&idx={self.gas_device_idx}&nvalue=0&svalue={data["usageGasTotal"]}')
                response_json = response.json()

                if response_json['status'] != 'OK':
                    raise Exception("Failed to push gas")

            except Exception as e:
                self.logger.error('Failed to push data to Domoticz', exc_info=e)

            time.sleep(10)

    def find_idx_devices(self):
        try:
            response = requests.get(f'{self.domoticz_url}/json.htm?type=command&param=devices_list')
            response_json = response.json()

            if response_json['status'] != 'OK':
                raise Exception(f'Get devices returned {response_json["status"]}')

            devices = response_json['result']
            electricity_device = next((d for d in devices if d['name'] == self.electricity_device_name), None)
            gas_device = next((d for d in devices if d['name'] == self.gas_device_name), None)

            if electricity_device is not None:
                self.electricity_device_idx = electricity_device['value']

            if gas_device is not None:
                self.gas_device_idx = gas_device['value']

        except Exception as e:
            self.logger.error('Failed to find devices', exc_info=e)
