import requests
import socket
import threading
import time
from abc import ABC, abstractmethod


class ElectionStatusHandler(ABC):

    @abstractmethod
    def handle_status(self, is_leader):
        pass


class Election(threading.Thread):

    CONSUL_BASE_URL = "http://localhost:8500/v1"
    CONSUL_SESSION_URL = CONSUL_BASE_URL + "/session/{}"
    CONSUL_KV_URL = CONSUL_BASE_URL + "/kv/{}"

    def __init__(self, election_key, time_step_seconds, election_status_handler):
        super().__init__()
        self._election_key = election_key
        self._time_step_seconds = time_step_seconds
        self._election_status_handler = election_status_handler
        self._session_id = self._create_consul_session()

    def _create_consul_session(self):
        response = requests.put(self.__class__.CONSUL_SESSION_URL.format("create"),
                                json={"Checks": ["serfHealth"]})

        response.raise_for_status()
        return response.json()["ID"]

    def _acquire_lock(self):
        response = requests.put(self.__class__.CONSUL_KV_URL.format(self._election_key),
                                params={"acquire": self._session_id},
                                json={"Name": socket.gethostname()})

        response.raise_for_status()
        return response.text == "true"

    def run(self):
        while True:
            is_leader = self._acquire_lock()
            proceed = self._election_status_handler.handle_status(is_leader)
            if not proceed:
                print("Status handler decided to abort election loop!")
                break

            print("Sleeping %d seconds ..." % self._time_step_seconds)
            time.sleep(self._time_step_seconds)

