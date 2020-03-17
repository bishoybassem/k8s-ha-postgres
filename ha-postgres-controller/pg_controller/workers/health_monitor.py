from pg_controller.workers import looping_thread
import requests
import logging
from abc import ABC, abstractmethod


class HealthCheck(ABC):

    def __init__(self, check_name, failure_threshold):
        super().__init__()
        self._check_name = check_name
        self._failure_threshold = failure_threshold
        self._failure_count = 0

    @property
    def check_name(self):
        return self._check_name

    def do_health_check(self):
        is_passing = self.do_health_check_impl()
        self._failure_count = 0 if is_passing else self._failure_count + 1
        return self._failure_count < self._failure_threshold

    @abstractmethod
    def do_health_check_impl(self):
        pass

    @abstractmethod
    def check_updated(self, is_passing):
        pass

    @abstractmethod
    def check_update_failed(self):
        pass

    @abstractmethod
    def continue_checking(self):
        pass


class HealthMonitor(looping_thread.LoopingThread):

    CONSUL_BASE_URL = "http://localhost:8500/v1"
    CONSUL_REGISTER_CHECK_URL = CONSUL_BASE_URL + "/agent/check/register"
    CONSUL_UPDATE_CHECK_URL = CONSUL_BASE_URL + "/agent/check/update/{}"

    def __init__(self, health_check, check_interval_seconds):
        super().__init__()
        self._health_check = health_check
        self._check_interval_seconds = check_interval_seconds
        self._create_consul_check()

    def _create_consul_check(self):
        ttl = self._check_interval_seconds + 5
        logging.info("Creating Consul TTL check: %s, with TTL: %ds", self._health_check.check_name, ttl)
        body = {
            "Name": self._health_check.check_name,
            "TTL": "%ds" % ttl,
        }

        response = requests.put(self.__class__.CONSUL_REGISTER_CHECK_URL, json=body)
        logging.info("Response (%d) %s", response.status_code, response.text)
        response.raise_for_status()

    def _update_consul_check(self, is_passing):
        status = "passing" if is_passing else "critical"
        logging.info("Updating Consul TTL check: %s, with status: %s", self._health_check.check_name, status)
        response = requests.put(self.__class__.CONSUL_UPDATE_CHECK_URL.format(self._health_check.check_name),
                                json={"Status": status})

        logging.info("Response (%d) %s", response.status_code, response.text)
        response.raise_for_status()

    def do_one_run(self):
        try:
            is_passing = self._health_check.do_health_check()
            self._update_consul_check(is_passing)
            self._health_check.check_updated(is_passing)
            if self._health_check.continue_checking() is False:
                self.stop()
        except:
            logging.exception("An error occurred during health check/update!")
            self._health_check.check_update_failed()

        self.wait(self._check_interval_seconds)
