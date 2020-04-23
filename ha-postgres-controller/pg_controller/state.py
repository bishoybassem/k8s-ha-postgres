import logging
import threading
import time
from functools import reduce

import requests

ROLE_MASTER = "Master"
ROLE_STANDBY = "Standby"
ROLE_DEAD_MASTER = "DeadMaster"
ALIVE_HEALTH_CHECK_NAME = "postgresAlive"
STANDBY_REPLICATION_HEALTH_CHECK_NAME = "postgresStandbyReplication"
CONSUL_BASE_URL = "http://localhost:8500/v1"


class State:
    """
    Holds the state of the controller, mainly the role of the monitored database along with the status of the health
    checks.
    """

    CONSUL_KV_URL = CONSUL_BASE_URL + "/kv/{}?raw"

    def __init__(self, consul_key_prefix, host_name):
        self._election_consul_key = consul_key_prefix + "/master"
        self._role_consul_key = "%s/%s/role" % (consul_key_prefix, host_name)
        self._role = None
        self._set_initial_role()
        self._health_checks = {
            ALIVE_HEALTH_CHECK_NAME: threading.Event(),
            STANDBY_REPLICATION_HEALTH_CHECK_NAME: threading.Event()
        }
        self._initialized = False

    @property
    def role(self):
        """Returns the role of the database: Master/Standby/DeadMaster."""
        return self._role

    @role.setter
    def role(self, role):
        """Sets the role of the database."""
        self._role = role

        logging.info("Setting Consul key: %s, to value: %s", self._role_consul_key, role)
        self._set_consul_key(self._role_consul_key, role)

    def set_health_check(self, name, is_passing):
        """Sets the status of the health check with the given name."""
        if is_passing is True:
            self._health_checks[name].set()
        else:
            self._health_checks[name].clear()

    def wait_till_healthy(self):
        """Blocks until each health check is set to passing."""
        for check in self._health_checks.values():
            check.wait()

    @property
    def initialized(self):
        """Returns whether the controller was initialized or not."""
        return self._initialized

    def done_initializing(self):
        """Marks the controller as initialized."""
        self._initialized = True

    @property
    def is_ready(self):
        """
        Returns whether the database is ready to accept connections or not (used as a K8s Readiness Probe). This
        property returns True if all the health checks are passing, and the controller is initialized properly. If
        the monitored database was master and failed ('DeadMaster' role), then False is returned unconditionally.
        """
        if self._role == ROLE_DEAD_MASTER:
            return False

        is_healthy = reduce(lambda x, y: x.is_set() and y.is_set(), self._health_checks.values())
        return self._initialized and is_healthy

    def _set_initial_role(self):
        """
        Sets the role of the database. If the election's consul key '$key_prefix/master' does not exist, then the
        assumed role is 'Master'. Otherwise, the previous role of this host is queried and assumed (key path
        '$key_prefix/$host_name/role'). Finally, if the election key exists, and no role has been assigned before, then
        the 'Standby' role is assumed.
        """
        logging.info("Checking whether the election key exists")
        if not self._query_consul_key(self._election_consul_key):
            self.role = ROLE_MASTER
            return

        logging.info("Querying the previous role of this host")
        assigned_role = self._query_consul_key(self._role_consul_key)
        if not assigned_role:
            self.role = ROLE_STANDBY
            return

        self._role = assigned_role

    def _query_consul_key(self, key):
        while True:
            try:
                response = requests.get(self.CONSUL_KV_URL.format(key))
                logging.info("Response (%d) %s", response.status_code, response.text)
                if response.status_code == 200:
                    return response.text
                if response.status_code == 404:
                    return None
            except:
                logging.exception("An error occurred while sending request to local consul client!")

            time.sleep(3)

    def _set_consul_key(self, key, value):
        response = requests.put(self.CONSUL_KV_URL.format(key), data=value)
        response.raise_for_status()
        logging.info("Response (%d) %s", response.status_code, response.text)


INSTANCE = None
