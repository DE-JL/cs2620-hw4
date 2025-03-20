import json
import uuid

from protos.chat_pb2 import *
from protos.chat_pb2_grpc import *

from utils import get_id_to_addr_map


def send_request(request: dict):
    id_to_addr = get_id_to_addr_map()

    for server_id, addr in id_to_addr.items():
        # Connect
        channel = grpc.insecure_channel(addr)
        stub = ChatStub(channel)

        # Send the request
        print(f"Sending request to server {server_id}")
        response = stub.Execute(ExecuteRequest(request=json.dumps(request)))
        print(response)

        # Parse the response
        response = json.loads(response.response)
        print(f"Received response from server {server_id}: {response}")


def create_user(username: str, password: str):
    request = {
        "id": str(uuid.uuid4()),
        "request_type": "AUTH",
        "action_type": "CREATE_USER",
        "username": username,
        "password": password,
    }
    send_request(request)


def login(username: str, password: str):
    request = {
        "id": uuid.uuid4(),
        "action_type": "LOGIN",
        "username": username,
        "password": password,
    }
    send_request(request)


def main():
    create_user("jason", "password")


if __name__ == "__main__":
    main()
