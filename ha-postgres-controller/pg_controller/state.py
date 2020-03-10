import threading
from functools import reduce

ROLE_MASTER = "Master"
ROLE_REPLICA = "Replica"
ROLE_DEAD_MASTER = "DeadMaster"
ALIVE_HEALTH_CHECK_NAME = "postgresAlive"
STANDBY_REPLICATION_HEALTH_CHECK_NAME = "postgresStandbyReplication"


class State:

    def __init__(self):
        self._role = None
        self._health_checks = {
            ALIVE_HEALTH_CHECK_NAME: threading.Event(),
            STANDBY_REPLICATION_HEALTH_CHECK_NAME: threading.Event()
        }
        self._initialized = False

    @property
    def role(self):
        return self._role

    @role.setter
    def role(self, role):
        self._role = role

    def set_health_check(self, name, is_passing):
        if is_passing is True:
            self._health_checks[name].set()
        else:
            self._health_checks[name].clear()

    def wait_till_healthy(self):
        for check in self._health_checks.values():
            check.wait()

    @property
    def initialized(self):
        return self._initialized

    def done_initializing(self):
        self._initialized = True

    @property
    def is_ready(self):
        if self._role == ROLE_DEAD_MASTER:
            return False

        is_healthy = reduce(lambda x, y: x.is_set() and y.is_set(), self._health_checks.values())
        return self._initialized and is_healthy


INSTANCE = State()
