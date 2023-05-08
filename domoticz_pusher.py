import logging
from threading import Thread
import threading
import time
from multiprocessing import Queue
import requests
from read_handler_interface import ReadHandlerInterface
from redis_queue import RedisQueue


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
            },
            'gas': {
                'name': f'P1 Gas ({self.dummy_device_name})',
                'sensor_type': '0xFB02',
                'idx': -1,
                'get_data': lambda device, data: f'{data["usageGasTotal"]}',
            }
        }

        if self.push_solar:
            self.devices['solar_general'] = {
                'name': f'Zonnepanelen ({self.dummy_device_name})',
                'sensor_type': '0xF31D',
                'idx': -1,
                'get_data': lambda device, data: f'{data["solarNow"]};'
                                                 f'{self.get_data_with_queue(device, data["solarTotal"])}',
                'change_device_url': lambda name, idx: f'/json.htm?type=setused&idx={idx}&name={name}'
                                                       f'&description=&switchtype=4&EnergyMeterMode=0&customimage=0'
                                                       f'&used=true',
                'queue': RedisQueue('solar_general')
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

            self.devices['solar_day_total'] = {
                'name': f'Zon Dag ({self.dummy_device_name})',
                'sensor_type': '0xF31F',
                'sensor_options': '&sensoroptions=1;KW',
                'idx': -1,
                'get_data': lambda device, data: f'{self.transform(device, data["allSolar"]["dayEnergy"], "KW")}',
                'queue': RedisQueue('solar_day_total')
            }

            self.devices['solar_year_total'] = {
                'name': f'Zon Jaar ({self.dummy_device_name})',
                'sensor_type': '0xF31F',
                'sensor_options': '&sensoroptions=1;KW',
                'idx': -1,
                'get_data': lambda device, data: f'{self.transform(device, data["allSolar"]["yearEnergy"], "KW")}',
                'queue': RedisQueue('solar_year_total')
            }

            self.devices['solar_total'] = {
                'name': f'Zon Totaal ({self.dummy_device_name})',
                'sensor_type': '0xF31F',
                'sensor_options': '&sensoroptions=1;MW',
                'idx': -1,
                'get_data': lambda device, data: f'{self.transform(device, data["allSolar"]["totalEnergy"], "MW")}',
                'queue': RedisQueue('solar_total')
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
    def get_data_with_queue(device, value):
        queue = device['queue']
        last_known = 0

        if not queue.empty():
            last_known = float(queue.get().decode('utf-8'))

        if value > 0:
            queue.put(value)
            return value

        if last_known > 0:
            queue.put(last_known)

        return last_known

    def transform(self, device, value, unit):
        if 'queue' in device:
            value = self.get_data_with_queue(device, value)

        if unit == 'MW':
            return f'{round(value / 1000_000, 3)}'
        elif unit == 'KW':
            return f'{round(value / 1000, 3)}'

        return f'{value}'

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
                    if 'value' in domoticz_device:
                        device['idx'] = domoticz_device['value']
                    elif 'idx' in domoticz_device:
                        device['idx'] = domoticz_device['idx']
                    else:
                        raise Exception('Encountered unknown domoticz_device format')
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

            create_url = f'{self.domoticz_url}/json.htm?type=createdevice&idx={hardware_idx}&sensorname={name}' \
                         f'&sensormappedtype={sensor_type}'

            if 'sensor_options' in device:
                create_url += device['sensor_options']

            response = requests.get(create_url)

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
