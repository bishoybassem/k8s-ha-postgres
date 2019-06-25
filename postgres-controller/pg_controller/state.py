
class State:

    def __init__(self):
        self._role = None
        self._initializing = True

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


ROLE_MASTER = "Master"
ROLE_SLAVE = "Slave"
INSTANCE = State()
