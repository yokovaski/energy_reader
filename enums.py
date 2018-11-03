from enum import Enum


class Thread(Enum):
    READER = 1
    DUMMY_READER = 2
    SENDER = 2


class Status(Enum):
    STOPPED = 1
    RUNNING = 2


class Error(Enum):
    UNAUTHORIZED = 1
    SERVER_UNREACHABLE = 2
