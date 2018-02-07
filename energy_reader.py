import requests, json
from uuid import getnode as get_mac
from dsmr_parser import telegram_specifications
from dsmr_parser.clients import SerialReader, SERIAL_SETTINGS_V4
from dsmr_parser import obis_references
import logging
import os
from urllib.request import urlopen
import time
import datetime

class Reader():
    def __init__(self):
        with open("config.json") as config_file:
            config = json.load(config_file)
            self.solar_ip = config["solar_ip"]
            self.solar_url = config["solar_url"]
            self.base_url = config["api_url"]
            self.key = config["secret"]

        self.store_energy_url = self.base_url + "/v1/energy"
        self.backup_file = "buffer.data"
        self.error_log = "error.log"

        self.set_mac_address()
        self.get_public_ip_address()
        self.set_raspberry_pi_id()
        self.set_token()

        if (self.file_length(self.backup_file) < 1):
            file = open(self.backup_file, 'w')
            file.close()

    def set_mac_address(self):
        mac = get_mac()
        self.mac_address = ':'.join(("%012X" % mac)[i:i + 2] for i in range(0, 12, 2))

    def get_public_ip_address(self):
        if os.environ.get("LOCAL") == "True":
            self.public_ip_address = "127.0.0.1"
        else:
            self.public_ip_address = json.loads(requests.get("http://jsonip.com").text)["ip"]

    def set_raspberry_pi_id(self):
        tokenValidation = {
            "key": self.key,
            "ip_address": self.public_ip_address,
            "mac_address": self.mac_address
        }

        url = self.base_url + "/v1/raspberrypis"
        headers = {"Content-type": "application/json", "Accept": "application/json"}

        response = requests.post(url, data=json.dumps(tokenValidation), headers=headers)
        response_data = json.loads(response.text)

        self.raspberry_pi_id = response_data["data"]["id"]
        self.client_id = response_data["data"]["client_id"]
        self.client_secret = response_data['data']["client_secret"]

    def set_token(self):
        token_validation = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret.encode("utf-8")
        }

        url = self.base_url + "/oauth/token"
        headers = {"Content-type": "application/x-www-form-urlencoded", "Accept": "application/json"}

        response = requests.post(url, data=token_validation, headers=headers)
        self.token = "Bearer " + json.loads(response.text)["access_token"].encode("utf-8")

    def file_length(sefl, fileName):
        if not os.path.isfile(fileName):
            return 0

        i = 0

        with open(fileName) as file:
            for i, l in enumerate(file):
                pass

        return i

    def read(self):
        logging.info("Setting up reader")

        serial_reader = SerialReader(
            device = "/dev/ttyUSB0",
            serial_settings = SERIAL_SETTINGS_V4,
            telegram_specification = telegram_specifications.V4
        )

        logging.info("Starting read")

        for telegram in serial_reader.read():
            self.send_telegram_to_api(telegram)

    def send_telegram_to_api(self, telegram):
        data = self.get_data_from_telegram(telegram)

        headers = {
            'Authorization': self.token,
            'Content-type': 'application/json',
            'Accept': 'application/json'
        }

        if self.previous_request_failed:
            self.send_back_up_data_to_api(headers)

        self.send_data_to_api(data, headers)

    def send_back_up_data_to_api(self, headers):
        with open(self.backup_file, 'rb') as file:
            content = file.readlines()
            content = [x.strip() for x in content]

            data = list()
            i = 0

            for line in content:
                dataRow = json.loads(line)
                data.append(dataRow)
                i += 1

            json_data = json.dumps({'data': data})

            try:
                response = requests.post(self.store_energy_url, data=json_data, headers=headers)

                if response.status_code == 401 and not self.retry:
                    self.set_token()
                    self.retry = True
                    self.send_back_up_data_to_api(headers)
                else:
                    self.write_error_to_log(response=response, data_send=json.dumps({'data': [data]}),
                                            url=self.store_energy_url)
                    return

            except requests.exceptions.ConnectionError:
                return

            file = open(self.backup_file, 'w')
            file.close()
            self.previous_request_failed = False

    def send_data_to_api(self, data, headers):
        try:
            response = requests.post(self.store_energy_url, data=json.dumps({'data': [data]}), headers=headers)

            if response.status_code == 401 and not self.retry:
                self.set_token()
                self.retry = True
                self.send_data_to_api(data, headers)
            else:
                self.write_error_to_log(response=response, data_send=json.dumps({'data': [data]}),
                                        url=self.store_energy_url)
        except requests.exceptions.ConnectionError:
            self.previous_request_failed = True
            self.buffer_backup_data(data)

    def get_data_from_telegram(self, telegram):
        solar = self.read_solar()

        data = {
            'raspberry_pi_id': self.raspberry_pi_id,
            'mode': str(telegram[obis_references.ELECTRICITY_ACTIVE_TARIFF].value),
            'usage_now': str(telegram[obis_references.CURRENT_ELECTRICITY_USAGE].value),
            'redelivery_now': str(telegram[obis_references.CURRENT_ELECTRICITY_DELIVERY].value),
            'solar_now': solar['now'],
            'usage_total_high': str(telegram[obis_references.ELECTRICITY_USED_TARIFF_2].value),
            'redelivery_total_high': str(telegram[obis_references.ELECTRICITY_DELIVERED_TARIFF_2].value),
            'usage_total_low': str(telegram[obis_references.ELECTRICITY_USED_TARIFF_1].value),
            'redelivery_total_low': str(telegram[obis_references.ELECTRICITY_DELIVERED_TARIFF_1].value),
            'solar_total': solar['total'],
            'usage_gas_now': "0",
            'usage_gas_total': str(telegram[obis_references.HOURLY_GAS_METER_READING].value)
        }

        return data

    def read_solar(self):
        solar = {
            "now": 0,
            "total": 0
        }

        if str(self.solar_ip) is "":
            return solar

        try:
            time.sleep(0.85)
            response = requests.get(url=self.solar_url, timeout=2)
            solar_data = json.loads(response.content)
            solar['now'] = solar_data['Body']['Data']['PAC']['Value']
            solar['total'] = solar_data['Body']['Data']['TOTAL_ENERGY']['Value']

            return solar
        except Exception:
            return solar

    def buffer_backup_data(self, data):
        time = datetime.datetime.utcnow().strftime("%Y-%m-%d %X")

        data['created_at'] = time
        data['updated_at'] = time

        file = open(self.backup_file, 'a')
        file.write(json.dumps(data) + "\n")
        file.close()

    def write_error_to_log(self, response, data_send, url):
        file = open(self.error_log, 'a')

        log = {
            "timestamp": datetime.datetime.utcnow().strftime("%Y-%m-%d %X"),
            "reponse":response,
            "status_code":response.status_code,
            "data_send":data_send,
            "url":url
        }

        file.write(json.dumps(log))
        file.close()

if __name__ == "__main__":
    app = Reader()
    app.read()