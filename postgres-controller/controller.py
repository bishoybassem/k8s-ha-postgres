from election import Election, ElectionResultHandler


class PostgresMasterElectionResultHandler(ElectionResultHandler):

    def leadership_acquired(self):
        print("I am currently the leader!")
        return True


def main():
    election = Election("service/postgres/master", 10, PostgresMasterElectionResultHandler())
    election.start()
    election.join()


if __name__ == '__main__':
    main()
