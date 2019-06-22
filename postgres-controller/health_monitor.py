import threading
import requests
import time
import logging
from abc import ABC, abstractmethod


class HealthCheck(ABC):

    @abstractmethod
    def do_health_check(self):
        pass


class HealthMonitor(threading.Thread):

    CONSUL_BASE_URL = "http://localhost:8500/v1"
    CONSUL_REGISTER_CHECK_URL = CONSUL_BASE_URL + "/agent/check/register"
    CONSUL_UPDATE_CHECK_URL = CONSUL_BASE_URL + "/agent/check/update/{}"

    def __init__(self, consul_check_name, health_check, time_step_seconds):
        super().__init__(name=self.__class__.__name__)
        self._consul_check_name = consul_check_name
        self._health_check = health_check
        self._time_step_seconds = time_step_seconds
        self._create_consul_check()

    def _create_consul_check(self):
        logging.info("Creating Consul TTL check for Postgres")
        body = {
            "Name": self._consul_check_name,
            "TTL": "%ds" % (self._time_step_seconds + 5),
            "Status": "passing"
        }

        response = requests.put(self.__class__.CONSUL_REGISTER_CHECK_URL, json=body)
        logging.info("Response (%d) %s" % (response.status_code, response.text))
        response.raise_for_status()

    def _update_consul_check(self, is_healthy):
        logging.info("Updating Consul TTL check for Postgres")
        response = requests.put(self.__class__.CONSUL_UPDATE_CHECK_URL.format(self._consul_check_name),
                                json={"Status": "passing" if is_healthy else "critical"})

        logging.info("Response (%d) %s" % (response.status_code, response.text))
        response.raise_for_status()

    def run(self):
        while True:
            is_healthy = self._health_check.do_health_check()
            self._update_consul_check(is_healthy)

            time.sleep(self._time_step_seconds)
