from pg_controller.workers import looping_thread
import requests
import logging
from abc import ABC, abstractmethod


class HealthCheck(ABC):
    """A base class that simplifies implementing health checks."""

    def __init__(self, check_name, failure_threshold):
        """
        :param check_name: The name of the check.
        :param failure_threshold: The number of consecutive failures for this check to be considered failed.
        """
        super().__init__()
        self._check_name = check_name
        self._failure_threshold = failure_threshold
        self._failure_count = 0

    @property
    def check_name(self):
        return self._check_name

    def do_health_check(self):
        """
        Executes the check defined by do_health_check_impl, and keeps track of the failure counts. This method
        returns True only if the number of failures exceeds the threshold set, otherwise, False.
        """
        is_passing = False
        try:
            is_passing = self.do_health_check_impl()
        except:
            logging.exception("An error occurred during health check!")

        self._failure_count = 0 if is_passing else self._failure_count + 1
        if self._failure_count > 0:
            logging.info("Failure count/threshold: %d/%d", self._failure_count, self._failure_threshold)

        return self._failure_count < self._failure_threshold

    @abstractmethod
    def do_health_check_impl(self):
        """Defines the check logic (to be implemented by subclasses)."""
        pass

    @abstractmethod
    def handle_status(self, is_passing):
        """
        Defines the logic to handle the check status (to be implemented by subclasses).
        """
        pass

    @abstractmethod
    def continue_checking(self):
        """
        Return True to signal the HealthMonitor thread to continue executing this check (to be implemented by
        subclasses).
        """
        pass


class HealthMonitor(looping_thread.LoopingThread):
    """
    Defines a Consul TTL check, keeps executing the supplied HealthCheck, and updates the Consul check status
    accordingly.
    """

    CONSUL_BASE_URL = "http://localhost:8500/v1"
    CONSUL_REGISTER_CHECK_URL = CONSUL_BASE_URL + "/agent/check/register"
    CONSUL_UPDATE_CHECK_URL = CONSUL_BASE_URL + "/agent/check/update/{}"

    def __init__(self, health_check, check_interval_seconds):
        """
        :param health_check: A HealthCheck instance that implements the check logic.
        :param check_interval_seconds: The time interval (in seconds) between two consecutive checks.
        """
        super().__init__(check_interval_seconds)
        self._health_check = health_check
        self._create_consul_check()

    def _create_consul_check(self):
        ttl = self._interval_seconds + 5
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
        """
        Executes the supplied HealthCheck's do_health_check method, then passes the result to the HealthCheck's
        handle_status method, It also updates the Consul check status with the result, and finally, evaluates the
        HealthCheck's continue_checking method to decide whether to stop or not.
        """
        is_passing = self._health_check.do_health_check()
        try:
            self._update_consul_check(is_passing)
        except:
            logging.exception("An error occurred during updating Consul's check!")

        self._health_check.handle_status(is_passing)
        if self._health_check.continue_checking() is False:
            logging.info("HealthCheck decided to stop the monitoring loop!")
            self.stop()
