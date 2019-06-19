import sys
from os import path
from election import Election, ElectionStatusHandler


class PostgresMasterElectionStatusHandler(ElectionStatusHandler):

    def __init__(self, out_dir):
        self._out_dir = out_dir

    def handle_status(self, is_leader):
        with open(path.join(self._out_dir, "role"), "w") as role_file:
            role_file.write("master" if is_leader else "slave")

        return True


def main():
    out_dir = sys.argv[1]
    election = Election("service/postgres/master", 10, PostgresMasterElectionStatusHandler(out_dir))
    election.start()
    election.join()


if __name__ == '__main__':
    main()
