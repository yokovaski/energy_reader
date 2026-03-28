import logging
import paho.mqtt.client as mqtt
import threading
import time
from multiprocessing import Queue
from read_handler_interface import ReadHandlerInterface
from threading import Thread


class MqttPublisher(Thread, ReadHandlerInterface):
    def __init__(self, config: dict, stop_event: threading.Event, logger: logging.Logger):
        super().__init__()

        self.queue: Queue = Queue()
        self.stop_event = stop_event
        self.logger = logger
        self.enabled = config["enabled"]
        self.connected = False
        self.mqtt_name = config["name"]
        self.mqtt_host = config["host"]
        self.mqtt_port = config["port"]
        self.mqtt_username = config["username"]
        self.mqtt_password = config["password"]
        self.mqtt_topic = config["topic"]
        self.connected = False
        self.last_run = None

        self.client = mqtt.Client()

    def seconds_since_last_run_time(self) -> float:
        if self.last_run is None:
            return None

        return time.time() - self.last_run

    def handle_read(self, data: dict) -> None:
        self.queue.put_nowait(data)

    def get_name(self) -> str:
        return f'MqttPublisher {self.mqtt_name}'

    def run(self):
        if not self.enabled:
            self.logger.info('MQTT Publisher is disabled')
            return

        self.logger.info(f'MQTT Publisher {self.mqtt_name} has been started')
        time_sent = time.time()

        while not self.stop_event.is_set():
            try:
                if self.queue.empty():
                    time.sleep(1)
                    continue

                if not self.is_connected():
                    time.sleep(5)
                    continue

                # Check if the time since the last message is more than 10 seconds to avoid flooding the MQTT broker
                if time.time() - time_sent < 10:
                    while not self.queue.empty():
                        self.queue.get_nowait()

                    continue

                data: dict = self.queue.get_nowait()
                self.publish(self.mqtt_topic, self.mqtt_topic, data)
                time_sent = time.time()
                self.last_run = time_sent
            except Exception as e:
                self.logger.error(f'Failed to push data to MQTT broker {self.mqtt_name}', exc_info=e)
                self.connected = False

                try:
                    self.client.loop_stop()
                    self.client.disconnect()
                except Exception as e:
                    self.logger.error(f'Failed to disconnect from MQTT broker {self.mqtt_name}', exc_info=e)

        if self.connected:
            self.client.loop_stop()
            self.client.disconnect()

        self.logger.info(f'MQTT Publisher {self.mqtt_name} has been terminated')

    def is_connected(self):
        if self.connected:
            return True

        try :
            self.client = mqtt.Client()
            self.client.username_pw_set(self.mqtt_username, self.mqtt_password)
            self.client.connect(self.mqtt_host, self.mqtt_port)
            self.client.loop_start()
            self.connected = True
            return True
        except Exception as e:
            self.logger.error(f'Failed to connect to MQTT broker {self.mqtt_name}', exc_info=e)

        return False

    def publish(self, topic, parent_key, value):
        # Check if value is a dictionary
        if isinstance(value, dict):
            for key, value in value.items():
                self.publish(topic + '/' + key, key, value)
        else:
            if parent_key == 'usageGasTotal':
                float_value = float(value)
                float_value = float_value / 1000
                result = self.client.publish(topic, float(float_value))
                self._check_publish_result(result, topic)
                return

            # Check if value is a float
            if isinstance(value, float):
                result = self.client.publish(topic, float(value))
            elif isinstance(value, int):
                result = self.client.publish(topic, int(value))
            else:
                result = self.client.publish(topic, str(value))

            self._check_publish_result(result, topic)

    def _check_publish_result(self, result, topic):
        if result.rc != mqtt.MQTT_ERR_SUCCESS:
            raise Exception(f'Failed to publish to topic {topic}: {mqtt.error_string(result.rc)}')