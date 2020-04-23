import logging
from abc import ABC, abstractmethod

import requests

from pg_controller.workers import looping_thread


class ElectionStatusHandler(ABC):

    @abstractmethod
    def handle_status(self, is_leader):
        """Defines the logic to handle the election status (to be implemented by subclasses)."""
        pass

    @abstractmethod
    def continue_participating(self):
        """Return True to signal the Election thread to continue participating (to be implemented by subclasses)."""
        pass


class Election(looping_thread.LoopingThread):
    """
    Creates a Consul session associated with the controllers health checks, and keeps trying to acquire the lock over
    the election key using the created session.
    """

    CONSUL_BASE_URL = "http://localhost:8500/v1"
    CONSUL_SESSION_URL = CONSUL_BASE_URL + "/session/{}"
    CONSUL_KV_URL = CONSUL_BASE_URL + "/kv/{}"

    def __init__(self, election_consul_key, consul_session_checks, election_status_handler, host_name, host_ip,
                 check_interval_seconds):
        """
         :param election_consul_key: The Consul key to acquire the lock over.
         :param consul_session_checks: The list of Consul check names to associate the session with.
         :param election_status_handler: An ElectionStatusHandler instance that handles the election status.
         :param host_name: The host name to set in the election key's value if the lock was acquired.
         :param host_ip: The IP to set in the election key's value if the lock was acquired.
         :param check_interval_seconds: The time interval (in seconds) between two consecutive attempts.
         """
        super().__init__(check_interval_seconds)
        self._election_consul_key = election_consul_key
        self._consul_session_checks = consul_session_checks
        self._election_status_handler = election_status_handler
        self._host_name = host_name
        self._host_ip = host_ip
        self._create_consul_session()

    def _create_consul_session(self):
        logging.info("Creating Consul session for leader election")
        response = requests.put(self.CONSUL_SESSION_URL.format("create"),
                                json={"Checks": self._consul_session_checks})

        logging.info("Response (%d) %s", response.status_code, response.text)
        response.raise_for_status()
        
        self._session_id = response.json()["ID"]

    def _acquire_lock(self):
        logging.info("Attempting to acquire lock over election key")
        response = requests.put(self.CONSUL_KV_URL.format(self._election_consul_key),
                                params={"acquire": self._session_id}, json={
                                    "host": self._host_ip,
                                    "node": self._host_name
                                })

        logging.info("Response (%d) %s", response.status_code, response.text)
        if response.status_code == 500 and "invalid session" in response.text:
            self._create_consul_session()
        else:
            response.raise_for_status()

        return response.text == "true"

    def do_one_run(self):
        """
        Attempts to acquire the lock over the election key using the created session, then passes the result to the
        ElectionStatusHandler's handle_status method. Finally, it evaluates the ElectionStatusHandler's
        continue_participating method to decide whether to stop or not.
        """
        try:
            is_leader = self._acquire_lock()
            self._election_status_handler.handle_status(is_leader)
        except:
            logging.exception("An error occurred during leader election!")

        if self._election_status_handler.continue_participating() is False:
            logging.info("ElectionStatusHandler decided to stop the election loop!")
            self.stop()
