
class State:

    def __init__(self):
        self._role = None
        self._initializing = True
        self._failed = False

    @property
    def role(self):
        return self._role

    @role.setter
    def role(self, role):
        self._role = role

    @property
    def initializing(self):
        return self._initializing

    def done_initializing(self):
        self._initializing = False

    def did_fail(self):
        self._failed = True

    @property
    def is_ready(self):
        return not (self._initializing or self._failed)


ROLE_MASTER = "Master"
ROLE_REPLICA = "Replica"
INSTANCE = State()
