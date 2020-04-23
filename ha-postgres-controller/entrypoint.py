import signal
import logging
import sys
from pg_controller.controller import Controller


logging.basicConfig(stream=sys.stdout, level=logging.INFO,
                    format='[%(asctime)s][%(threadName)s] %(levelname)s: %(message)s')

controller_process = Controller()
signal.signal(signal.SIGTERM, controller_process.stop)
controller_process.start()
