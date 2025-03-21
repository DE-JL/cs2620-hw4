import json
import sys
import uuid

from protos.chat_pb2 import *
from protos.chat_pb2_grpc import *

from config import LOCALHOST
from utils import get_id_to_addr_map


def send_request(request: dict, server_addr: str) -> dict | None:
    """
    Send a request to multiple servers and return the last successful response.

    :param request: The request object.
    :param server_addr: The IP address of the server.
    :return: The response object.
    """
    # Get the map from server ID to IP address and port
    id_to_addr = get_id_to_addr_map(server_addr)

    response = None
    for server_id, addr in id_to_addr.items():
        channel = None
        try:
            # Connect to server
            channel = grpc.insecure_channel(addr)
            stub = ChatStub(channel)

            # Send the request
            response = stub.Execute(ExecuteRequest(request=json.dumps(request)))

            # Parse the response
            response = json.loads(response.response)

            # Log
            print(f"Sent request to server {server_id}: {json.dumps(request, indent=4)}")
            print(f"Received response from server {server_id}: {json.dumps(response, indent=4)}\n")
        except grpc.RpcError as e:
            if e.code() == grpc.StatusCode.UNKNOWN:
                print(e)
                sys.exit(1)
        finally:
            if channel is not None:
                channel.close()

    assert isinstance(response, dict), "Invalid response format."
    return response


def create_user(username: str, password: str, server_addr: str = LOCALHOST) -> dict:
    """
    Creates a new user with the given username and password by sending a
    request to create the user in the system. The method generates a unique
    identifier for the request and sets the request type.

    :param username: The username of the new user.
    :param password: The password of the new user.
    :param server_addr: The IP address of the server. Defaults to localhost.
    :return: The response object.
    """
    request = {
        "id": str(uuid.uuid4()),
        "request_type": "CREATE_USER",
        "username": username,
        "password": password,
    }
    return send_request(request, server_addr)


def login(username: str, password: str, server_addr: str = LOCALHOST) -> dict:
    """
    Sends a login request for user authentication. This function constructs
    a request with a unique identifier, request type, and user credentials.
    The request is then dispatched for processing.

    :param username: The username of the user attempting to log in.
    :param password: The password associated with the username.
    :param server_addr: The IP address of the server. Defaults to localhost.
    :return: The response object.
    """
    request = {
        "id": str(uuid.uuid4()),
        "request_type": "LOGIN",
        "username": username,
        "password": password,
    }
    return send_request(request, server_addr)


def get_messages(username: str, server_addr: str = LOCALHOST) -> dict:
    """
    Fetches messages for a given username by sending a request.

    The function generates a unique request identifier and creates a request
    object containing the type of request and the username. It then sends this
    request to fetch messages associated with the specified username.

    :param username: The username for which to retrieve messages.
    :param server_addr: The IP address of the server. Defaults to localhost.
    :return: The response object.
    """
    request = {
        "id": str(uuid.uuid4()),
        "request_type": "GET_MESSAGES",
        "username": username,
    }
    return send_request(request, server_addr)


def list_users(pattern: str, server_addr: str = LOCALHOST) -> dict:
    """
    Lists the users matching a specified pattern. This function generates a unique
    request ID, prepares a request dictionary with the specified pattern for
    matching, and sends the request to an external system using `send_request`.
    The result is returned as a dictionary.

    :param pattern: The pattern used to filter users.
    :param server_addr: The IP address of the server. Defaults to localhost.
    :return: The response object.
    """
    request = {
        "id": str(uuid.uuid4()),
        "request_type": "LIST_USERS",
        "pattern": pattern,
    }
    return send_request(request, server_addr)


def send_message(message: dict, server_addr: str = LOCALHOST) -> dict:
    """
    Sends a message from a sender to a recipient with a specified message body.
    This function creates a unique request ID and message ID, includes a timestamp
    for when the message is being sent, and formats the data into a request object.
    The request is then sent using the `send_request` function to handle the actual
    dispatching operation.

    :param message: The message object.
    :param server_addr: The IP address of the server. Defaults to localhost.
    :return: The response object.
    """
    request = {
        "id": str(uuid.uuid4()),
        "request_type": "SEND_MESSAGE",
        "message": message,
    }
    return send_request(request, server_addr)


def read_messages(message_ids: list[str], server_addr: str = LOCALHOST) -> dict:
    """
    Reads the specified messages by their unique identifiers. This function generates
    a unique request ID and constructs a request to read the messages. The request
    type is set to "READ_MESSAGES" and includes the provided message IDs. The
    constructed request is then sent, and the response is returned.

    :param message_ids: A list of unique identifiers for the messages to be read.
    :param server_addr: The IP address of the server. Defaults to localhost.
    :return: The response object.
    """
    request = {
        "id": str(uuid.uuid4()),
        "request_type": "READ_MESSAGES",
        "message_ids": message_ids,
    }
    return send_request(request, server_addr)


def delete_messages(message_ids: list[str], server_addr: str = LOCALHOST) -> dict:
    """
    Deletes a list of messages based on their unique identifiers. This function
    sends a request to delete the specified messages and returns a response
    indicating the result of the operation.

    :param message_ids: The list of unique identifiers of the messages to be deleted.
    :param server_addr: The IP address of the server. Defaults to localhost.
    :return: The response object.
    """
    request = {
        "id": str(uuid.uuid4()),
        "request_type": "DELETE_MESSAGES",
        "message_ids": message_ids,
    }
    return send_request(request, server_addr)


def delete_user(username: str, server_addr: str = LOCALHOST) -> dict:
    """
    Deletes a user profile identified by the provided username. This function
    creates a request object containing a unique identifier and request type,
    used to instruct the server to process the user deletion. It invokes a
    helper function to send this request and handles the result.

    :param username: The username of the user to delete.
    :param server_addr: The IP address of the server. Defaults to localhost.
    :return: The response object.
    """
    request = {
        "id": str(uuid.uuid4()),
        "request_type": "DELETE_USER",
        "username": username,
    }
    return send_request(request, server_addr)
