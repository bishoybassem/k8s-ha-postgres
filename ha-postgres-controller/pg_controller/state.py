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

    @property
    def healthy(self):
        return reduce(lambda x, y: x.is_set() and y.is_set(), self._health_checks.values())

    def set_health_check(self, name, is_passing):
        if is_passing:
            self._health_checks[name].set()
        else:
            self._health_checks[name].clear()

        if self._role == ROLE_MASTER and self._initialized and name == ALIVE_HEALTH_CHECK_NAME and not is_passing:
            self._role = ROLE_DEAD_MASTER

    def wait_till_healthy(self):
        for check in self._health_checks.values():
            check.wait()

    def done_initializing(self):
        self._initialized = True

    @property
    def is_ready(self):
        if self._role == ROLE_DEAD_MASTER:
            return False

        return self._initialized and self.healthy


INSTANCE = State()
