from enum import Enum


class Thread(Enum):
    READER = "READER"
    DUMMY_READER = "DUMMY_READER"
    SENDER = "SENDER"


class Status(Enum):
    STOPPED = "STOPPED"
    RUNNING = "RUNNING"


class Error(Enum):
    UNAUTHORIZED = "UNAUTHORIZED"
    SERVER_UNREACHABLE = "SERVER_UNREACHABLE"
    READING = "READING"
    SOLAR_API = "SOLAR_API"
