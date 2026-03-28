import copy
import json
import logging
import time

from read_handler_interface import ReadHandlerInterface
from redis_queue import RedisQueue


class RedisPusher(ReadHandlerInterface):
    def __init__(self, logger: logging.Logger, queue_names):
        self.redis_queues = []

        for queue_name in queue_names:
            self.redis_queues.append(RedisQueue(f'normal_{queue_name}'))

        self.logger: logging.Logger = logger
        self.last_run = None

    def handle_read(self, data: dict) -> None:
        energy_data = copy.deepcopy(data)
        energy_data.pop('allSolar')

        for redis_queue in self.redis_queues:
            try:
                redis_queue.put(json.dumps(energy_data))
            except Exception as e:
                self.logger.error(f'Failed to put data in redis queue ({redis_queue.key})', exc_info=e)

        self.last_run = time.time()

    def get_name(self) -> str:
        return 'RedisPusher'

    def seconds_since_last_run_time(self) -> float:
        if self.last_run is None:
            return None

        return time.time() - self.last_run
