import time
import threading
import queue


class Sender(threading.Thread):
    def __init__(self, energy_data_queue, stop_event):
        super(Sender, self).__init__()

        self.energy_data_queue = energy_data_queue
        self.stop_event = stop_event

    def run(self):
        while not self.stop_event.is_set():
            try:
                data = self.energy_data_queue.get(False)
                self.send_data_to_api(data)
            except queue.Empty:
                time.sleep(1)

    def send_data_to_api(self, data):
        do_something = ""

