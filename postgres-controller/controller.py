import requests
import socket
import base64
import json


def create_consul_session():
    response = requests.put("http://localhost:8500/v1/session/create",
                            json={"Name": "postgresMaster", "Checks": ["serfHealth"]})

    response.raise_for_status()
    return response.json()["ID"]


def try_to_be_master(session_id):
    response = requests.put("http://localhost:8500/v1/kv/service/postgres/master",
                            params={"acquire": session_id},
                            json={"Name": socket.gethostname()})

    return response.text == "true"


def get_current_master():
    response = requests.get("http://localhost:8500/v1/kv/service/postgres/master")
    response.raise_for_status()
    value_b64 = response.json()[0]["Value"]
    value = str(base64.b64decode(value_b64), 'utf-8')
    name = json.loads(value)["Name"]
    return name


def main():
    session_id = create_consul_session()
    try_to_be_master(session_id)
    print(get_current_master())


if __name__ == '__main__':
    main()
