import logging
from threading import Thread
import threading
import time
from multiprocessing import Queue
import requests
from read_handler_interface import ReadHandlerInterface


class DomoticzPusher(Thread, ReadHandlerInterface):
    def __init__(self, config: dict, stop_event: threading.Event, logger: logging.Logger, push_solar: bool):
        super().__init__()

        self.queue: Queue = Queue()
        self.stop_event = stop_event
        self.logger = logger
        self.connected = False
        self.domoticz_url = config['domoticz_url']
        self.dummy_device_name = config['domoticz_dummy_name']
        self.push_solar = push_solar
        self.devices = {}

        self.set_devices_to_default()

    def set_devices_to_default(self):
        self.devices = {
            'electricity': {
                'name': f'P1 Elektriciteit ({self.dummy_device_name})',
                'sensor_type': '0xFA01',
                'idx': -1,
                'get_data': lambda device, data: f'{data["usageTotalHigh"]};{data["usageTotalLow"]};'
                                         f'{data["redeliveryTotalHigh"]};{data["redeliveryTotalLow"]};'
                                         f'{data["usageNow"]};{data["redeliveryNow"]}',
                'should_send': lambda data: True
            },
            'gas': {
                'name': f'P1 Gas ({self.dummy_device_name})',
                'sensor_type': '0xFB02',
                'idx': -1,
                'get_data': lambda device, data: f'{data["usageGasTotal"]}',
                'should_send': lambda data: True
            }
        }

        if self.push_solar:
            self.devices['solar_general'] = {
                'name': f'Zonnepanelen ({self.dummy_device_name})',
                'sensor_type': '0xF31D',
                'idx': -1,
                'get_data': lambda device, data: self.get_solar_data_and_store_total(device, data),
                'change_device_url': lambda name, idx: f'/json.htm?type=setused&idx={idx}&name={name}'
                                                       f'&description=&switchtype=4&EnergyMeterMode=0&customimage=0'
                                                       f'&used=true',
                'last_total': 0
            }

            self.devices['solar_iac'] = {
                'name': f'IAC ({self.dummy_device_name})',
                'sensor_type': '0xF317',
                'idx': -1,
                'get_data': lambda device, data: f'{data["allSolar"]["iac"]}'
            }

            self.devices['solar_idc'] = {
                'name': f'IDC ({self.dummy_device_name})',
                'sensor_type': '0xF317',
                'idx': -1,
                'get_data': lambda device, data: f'{data["allSolar"]["idc"]}'
            }

            self.devices['solar_uac'] = {
                'name': f'UAC ({self.dummy_device_name})',
                'sensor_type': '0xF308',
                'idx': -1,
                'get_data': lambda device, data: f'{data["allSolar"]["uac"]}'
            }

            self.devices['solar_udc'] = {
                'name': f'UDC ({self.dummy_device_name})',
                'sensor_type': '0xF308',
                'idx': -1,
                'get_data': lambda device, data: f'{data["allSolar"]["udc"]}'
            }

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

                for device in self.devices.values():
                    self.push_data_to_domoticz(device, data)

            except Exception as e:
                self.logger.error('Failed to push data to Domoticz', exc_info=e)
                self.reset()

    def push_data_to_domoticz(self, device, data):
        s_value = device['get_data'](device, data)

        self.logger.debug(f'Sending data to domoticz for {device["name"]}: {s_value}')
        response = requests.get(f'{self.domoticz_url}/json.htm?type=command&param=udevice&'
                                f'idx={device["idx"]}&nvalue=0&svalue={s_value}')
        if not response.ok:
            raise Exception(f'Received unexpected status code on pushing {device["name"]}: {response.status_code}')

        response_json = response.json()

        if response_json['status'] != 'OK':
            raise Exception(f'Failed to push {device["name"]}, received status: {response_json["status"]}')

    @staticmethod
    def get_solar_data_and_store_total(device, data):
        solar_total = data['solarTotal']

        # Use the last known total when the given total is 0 (solar system is down)
        if solar_total == 0:
            solar_total = device['last_total']
        else:
            device['last_total'] = solar_total

        return f'{data["solarNow"]};{solar_total}'

    def reset(self):
        self.connected = False
        self.set_devices_to_default()

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

            if not response.ok:
                raise Exception(f'Received unexpected status code on get hardware: {response.status_code}')

            response_json = response.json()

            if response.ok and response_json['status'] != 'OK':
                raise Exception(f'Get devices returned {response_json["status"]}')

            devices = response_json['result'] if 'result' in response_json else []

            for device in self.devices.values():
                domoticz_device = next((d for d in devices if d['name'] == device['name']), None)

                if domoticz_device is not None:
                    device['idx'] = domoticz_device['value']
                else:
                    found_all_devices = False

        except Exception as e:
            self.logger.error('Failed to locate devices', exc_info=e)

        return found_all_devices

    def try_store_hardware(self) -> bool:
        try:
            response = requests.get(f'{self.domoticz_url}/json.htm?type=hardware')

            if not response.ok:
                raise Exception(f'Received unexpected status code on get hardware: {response.status_code}')

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

                if device['Name'] != self.dummy_device_name:
                    continue

                dummy_device_idx = device['idx']
                break

            if dummy_device_idx is None:
                self.logger.info(f'Creating new domoticz dummy device with name "{self.dummy_device_name}"')
                response = requests.get(f'{self.domoticz_url}/json.htm?type=command&param=addhardware&htype=15&port=1'
                                        f'&name={self.dummy_device_name}&enabled=true')

                if not response.ok:
                    raise Exception(f'Received unexpected status code on creating dummy hardware '
                                    f'{self.dummy_device_name}: {response.status_code}')

                response_json = response.json()

                if not response_json['status'] == 'OK':
                    raise Exception(f'Create dummy hardware returned {response_json["status"]}')

                dummy_device_idx = response_json['idx']

            for device in self.devices.values():
                idx = device['idx']
                if idx == -1:
                    idx = self.try_store_device(dummy_device_idx, device)

                    if idx is None:
                        return False

                    device['idx'] = idx

            return True
        except Exception as e:
            self.logger.error('Failed to store devices', exc_info=e)
            return False

    def try_store_device(self, hardware_idx, device) -> str or None:
        name = device['name']
        sensor_type = device['sensor_type']

        try:

            self.logger.info(f'Creating new domoticz sensor with name "{name}"')

            response = requests.get(f'{self.domoticz_url}/json.htm?type=createdevice&idx={hardware_idx}'
                                    f'&sensorname={name}&sensormappedtype={sensor_type}')

            if not response.ok:
                raise Exception(f'Received unexpected status code on creating device {name}: {response.status_code}')

            response_json = response.json()

            if not response_json['status'] == 'OK':
                raise Exception(f'Create device returned {response_json["status"]} when creating sensor with type '
                                f'{sensor_type}')

            idx = response_json['idx']

            if 'change_device_url' in device:
                response = requests.get(f'{self.domoticz_url}{device["change_device_url"](name, idx)}')

                if not response.ok:
                    raise Exception(
                        f'Received unexpected status code on changing device {name}: {response.status_code}')

                response_json = response.json()

                if not response_json['status'] == 'OK':
                    raise Exception(f'Create device returned {response_json["status"]} when change sensor with type '
                                    f'{sensor_type}')

            return idx
        except Exception as e:
            self.logger.error(f'Failed to create device {name}', exc_info=e)
            return None
