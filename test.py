#!/usr/bin/env python3
import time
import logging
import logging.handlers
from subprocess import call
import threading

class TestApp(threading.Thread):
    def __init__(self, name):
        threading.Thread.__init__(self)
        self.name = name
        self.my_logger = logging.getLogger('MyLogger')
        self.my_logger.setLevel(logging.DEBUG)

        handler = logging.handlers.SysLogHandler(address='/dev/log')

        self.my_logger.addHandler(handler)

        self.my_logger.debug('this is debug')
        self.my_logger.critical('this is critical')

        self.keep_running = True

    def run(self):
        i = 0

        while self.keep_running:
            self.my_logger.info("Hi, I am %s and is number %d" % (self.name, i))
            # logging.info("Hi, I am %s" % self.name)
            # print("Hi, I am %s" % self.name)
            time.sleep(1)
            i += 1

    def launch_script(self, script):
        call(script)

if __name__ == "__main__":
    app = TestApp("Test")
    app.run()