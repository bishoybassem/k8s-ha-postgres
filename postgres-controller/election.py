import requests
import socket
import base64
import json
import threading
import time
from abc import ABC, abstractmethod


class ElectionResultHandler(ABC):

    @abstractmethod
    def leadership_acquired(self):
        pass


class Election(threading.Thread):

    CONSUL_BASE_URL = "http://localhost:8500/v1"
    CONSUL_SESSION_URL = CONSUL_BASE_URL + "/session/{}"
    CONSUL_KV_URL = CONSUL_BASE_URL + "/kv/{}"

    def __init__(self, election_key, time_step_seconds, election_result_handler):
        super().__init__()
        self._election_key = election_key
        self._time_step_seconds = time_step_seconds
        self._election_result_handler = election_result_handler
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

    def get_current_leader(self):
        response = requests.get(self.__class__.CONSUL_KV_URL.format(self._election_key))
        response.raise_for_status()
        value_b64 = response.json()[0]["Value"]
        value = str(base64.b64decode(value_b64), 'utf-8')
        name = json.loads(value)["Name"]
        return name

    def run(self):
        while True:
            if self._acquire_lock():
                print("Leadership lock acquired!")
                proceed = self._election_result_handler.leadership_acquired()
                if not proceed:
                    print("Result handler decided to abort election loop!")
                    break

            print("Sleeping %d seconds ..." % self._time_step_seconds)
            time.sleep(self._time_step_seconds)



