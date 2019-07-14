from pg_controller.workers import looping_thread
import requests
import logging
from abc import ABC, abstractmethod


class HealthCheck(ABC):

    @abstractmethod
    def do_health_check(self):
        pass

    @abstractmethod
    def check_updated(self, is_healthy):
        pass

    @abstractmethod
    def check_update_failed(self):
        pass


class HealthMonitor(looping_thread.LoopingThread):

    CONSUL_BASE_URL = "http://localhost:8500/v1"
    CONSUL_REGISTER_CHECK_URL = CONSUL_BASE_URL + "/agent/check/register"
    CONSUL_UPDATE_CHECK_URL = CONSUL_BASE_URL + "/agent/check/update/{}"

    def __init__(self, consul_check_name, health_check, time_step_seconds):
        super().__init__()
        self._consul_check_name = consul_check_name
        self._health_check = health_check
        self._time_step_seconds = time_step_seconds
        self._create_consul_check()

    def _create_consul_check(self):
        logging.info("Creating Consul TTL check for Postgres")
        body = {
            "Name": self._consul_check_name,
            "TTL": "%ds" % (self._time_step_seconds + 5),
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

    def do_one_run(self):
        try:
            is_healthy = self._health_check.do_health_check()
            self._update_consul_check(is_healthy)
            self._health_check.check_updated(is_healthy)
        except:
            logging.exception("An error occurred during health check/update!")
            self._health_check.check_update_failed()

        self.wait(self._time_step_seconds)
