import threading


class State:

    def __init__(self):
        self._role = None
        self._healthy = threading.Event()
        self._initialized = False
        self._failed_after_initialized = False

    @property
    def role(self):
        return self._role

    @role.setter
    def role(self, role):
        self._role = role

    @property
    def healthy(self):
        return self._healthy.is_set()

    @healthy.setter
    def healthy(self, healthy):
        if healthy:
            self._healthy.set()
        else:
            self._healthy.clear()
            if self._initialized:
                self._failed_after_initialized = True

    def wait_till_healthy(self):
        self._healthy.wait()

    def done_initializing(self):
        self._initialized = True

    @property
    def is_ready(self):
        return self._initialized and self.healthy and not self._failed_after_initialized


ROLE_MASTER = "Master"
ROLE_REPLICA = "Replica"
INSTANCE = State()
