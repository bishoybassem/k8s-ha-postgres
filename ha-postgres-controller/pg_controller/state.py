import threading
from functools import reduce

ROLE_MASTER = "Master"
ROLE_STANDBY = "Standby"
ROLE_DEAD_MASTER = "DeadMaster"
ALIVE_HEALTH_CHECK_NAME = "postgresAlive"
STANDBY_REPLICATION_HEALTH_CHECK_NAME = "postgresStandbyReplication"


class State:
    """
    Holds the state of the controller, mainly the role of the monitored database along with the status of the health
    checks.
    """

    def __init__(self):
        self._role = None
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


INSTANCE = State()
