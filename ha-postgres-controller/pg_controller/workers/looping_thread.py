import threading
import logging


class LoopingThread(threading.Thread):
    """A base class that helps in implementing repeating tasks."""

    def __init__(self, interval_seconds):
        """
        :param interval_seconds: The time interval (in seconds) between two consecutive task executions.
        """
        super().__init__(name=self.__class__.__name__)
        self._exit = threading.Event()
        self._interval_seconds = interval_seconds

    def do_one_run(self):
        """Defines the task logic (to be implemented by subclasses)."""
        pass

    def run(self):
        while not self._exit.is_set():
            self.do_one_run()
            self._exit.wait(self._interval_seconds)

        logging.info("Stopped!")

    def stop(self):
        logging.info("Stopping %s thread...", self.name)
        self._exit.set()

