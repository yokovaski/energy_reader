"""Test doubles shared by the test_*.py files."""
import json
from unittest import mock


class FakeRedisQueue:
    """In-memory stand-in for RedisQueue; get() returns bytes like redis does."""

    def __init__(self, name='fake', *items):
        self.key = f'queue:{name}'
        self.items = list(items)

    def qsize(self):
        return len(self.items)

    def empty(self):
        return not self.items

    def put(self, item):
        self.items.append(item)

    def get(self, block=True, timeout=None):
        return str(self.items.pop(0)).encode('utf-8') if self.items else None

    def get_nowait(self):
        return self.get(False)


def json_queue(*messages):
    return FakeRedisQueue('json', *[json.dumps(m) for m in messages])


def response(status_code=200, body=None):
    """requests.Response stand-in."""
    r = mock.Mock()
    r.status_code = status_code
    r.ok = status_code < 400
    r.json.return_value = body if body is not None else {}
    r.text = json.dumps(r.json.return_value)
    return r


def stop_after(event, calls=1):
    """time.sleep replacement that sets the stop event after `calls` sleeps."""
    state = {'n': 0}

    def sleep(_seconds):
        state['n'] += 1
        if state['n'] >= calls:
            event.set()

    return sleep
