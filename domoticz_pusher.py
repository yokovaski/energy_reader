import logging
from threading import Thread
import threading
import time
from queue import Queue
import requests
from read_handler_interface import ReadHandlerInterface


class DomoticzPusher(Thread, ReadHandlerInterface):
    def __init__(self, config: dict, stop_event: threading.Event, logger: logging.Logger):
        super().__init__()
        
        self.queue = Queue()
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
            if self.queue.empty():
                time.sleep(1)
                continue

            if not self.is_connected():
                time.sleep(10)
                continue

            try:
                data: dict = self.queue.get_nowait()

                s_value = f'{data["usageTotalHigh"]};{data["usageTotalLow"]};{data["redeliveryTotalHigh"]};' \
                          f'{data["redeliveryTotalLow"]};{data["usageNow"]};{data["redeliveryNow"]}'
                response = requests.get(f'{self.domoticz_url}/json.htm?type=command&param=udevice&'
                                        f'idx={self.electricity_device_idx}&nvalue=0&svalue={s_value}')
                response_json = response.json()

                if response_json['status'] != 'OK':
                    raise Exception("Failed to push electricity")

                response = requests.get(f'{self.domoticz_url}/json.htm?type=command&param=udevice&'
                                        f'idx={self.gas_device_idx}&nvalue=0&svalue={data["usageGasTotal"]}')
                response_json = response.json()

                if response_json['status'] != 'OK':
                    raise Exception("Failed to push gas")

            except Exception as e:
                self.logger.error('Failed to push data to Domoticz', exc_info=e)
                self.reset()

    def reset(self):
        self.connected = False
        self.electricity_device_idx = -1
        self.gas_device_idx = -1

    def is_connected(self) -> bool:
        if self.connected:
            return True

        response = requests.get(f'{self.domoticz_url}/json.htm?type=command&param=getversion')
        response_data = response.json()

        if response.ok and response_data['status'] == 'OK':
            success = self.try_find_idx_devices()

            if not success:
                success = self.try_store_hardware()

            self.connected = success
            return True
        else:
            return False

    def try_find_idx_devices(self) -> bool:
        found_all_devices = True

        try:
            response = requests.get(f'{self.domoticz_url}/json.htm?type=command&param=devices_list')
            response_json = response.json()

            if response.ok and response_json['status'] != 'OK':
                raise Exception(f'Get devices returned {response_json["status"]}')

            devices = response_json['result'] if 'result' in response_json else []
            electricity_device = next((d for d in devices if d['name'] == self.electricity_device_name), None)
            gas_device = next((d for d in devices if d['name'] == self.gas_device_name), None)

            if electricity_device is not None:
                self.electricity_device_idx = electricity_device['value']
            else:
                found_all_devices = False

            if gas_device is not None:
                self.gas_device_idx = gas_device['value']
            else:
                found_all_devices = False

        except Exception as e:
            self.logger.error('Failed to find devices', exc_info=e)

        return found_all_devices

    def try_store_hardware(self) -> bool:
        hardware_name = 'EnergieZicht'

        try:
            response = requests.get(f'{self.domoticz_url}/json.htm?type=hardware')
            response_json = response.json()

            if not response_json['status'] == 'OK':
                raise Exception(f'Get hardware returned {response_json["status"]}')

            dummy_device_idx = None
            hardware = response_json['result'] if 'result' in response_json else []

            for device in hardware:
                if device['Enabled'] != 'true':
                    continue

                if device['Type'] != 15:
                    continue

                if device['Name'] != hardware_name:
                    continue

                dummy_device_idx = device['idx']
                break

            if dummy_device_idx is None:
                self.logger.info('Creating new domoticz dummy device with name "EnergieZicht"')
                response = requests.get(f'{self.domoticz_url}/json.htm?type=command&param=addhardware&htype=15&port=1'
                                        f'&name={hardware_name}&enabled=true')
                response_json = response.json()

                if not response_json['status'] == 'OK':
                    raise Exception(f'Get hardware returned {response_json["status"]}')

                dummy_device_idx = response_json['idx']

            if self.electricity_device_idx == -1:
                electricity_idx = self.try_store_device(dummy_device_idx, self.electricity_device_name, '0xFA01')
                if electricity_idx is None:
                    return False

                self.electricity_device_idx = electricity_idx

            if self.gas_device_idx == -1:
                gas_idx = self.try_store_device(dummy_device_idx, self.gas_device_name, '0xFB02')
                if gas_idx is None:
                    return False

                self.gas_device_idx = gas_idx

            return True
        except Exception as e:
            self.logger.error('Failed to store devices', exc_info=e)
            return False

    def try_store_device(self, hardware_idx, name, sensor_type) -> str or None:
        try:
            self.logger.info(f'Creating new domoticz sensor with name "{name}"')

            response = requests.get(f'{self.domoticz_url}/json.htm?type=createdevice&idx={hardware_idx}'
                                    f'&sensorname={name}&sensormappedtype={sensor_type}')
            response_json = response.json()

            if not response_json['status'] == 'OK':
                raise Exception(f'Create device returned {response_json["status"]} when creating sensor with type '
                                f'{sensor_type}')

            return response_json['idx']
        except Exception as e:
            self.logger.error(f'Failed to create device {name}', exc_info=e)
            return None
