import copy
import json
import logging

from read_handler_interface import ReadHandlerInterface
from redis_queue import RedisQueue


class RedisPusher(ReadHandlerInterface):
    def __init__(self, logger: logging.Logger):
        self.energy_data_queue = RedisQueue('normal')
        self.logger: logging.Logger = logger

    def handle_read(self, data: dict) -> None:
        energy_data = copy.deepcopy(data)
        energy_data.pop('allSolar')
        self.energy_data_queue.put(json.dumps(energy_data))

    def get_name(self) -> str:
        return 'RedisPusher'
