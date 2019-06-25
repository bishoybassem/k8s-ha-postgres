import threading
import logging


class LoopingThread(threading.Thread):

    def __init__(self):
        super().__init__(name=self.__class__.__name__)
        self._exit = threading.Event()

    def do_one_run(self):
        pass

    def cleanup(self):
        pass

    def run(self):
        while not self._exit.is_set():
            self.do_one_run()

        self.cleanup()
        logging.info("Stopped!")

    def stop(self):
        logging.info("Stopping %s thread ..." % self.name)
        self._exit.set()

    def wait(self, timeout):
        self._exit.wait(timeout)

