import copy
import json

from read_handler_interface import ReadHandlerInterface
from redis_queue import RedisQueue


class RedisPusher(ReadHandlerInterface):
    def __init__(self, logger):
        self.energy_data_queue = RedisQueue('normal')
        self.logger = logger

    def handle_read(self, data) -> None:
        energy_data = copy.deepcopy(data)
        energy_data.pop('allSolar')
        self.energy_data_queue.put(json.dumps(energy_data))

    def get_name(self) -> str:
        return 'RedisPusher'
