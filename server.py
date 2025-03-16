import uuid

from concurrent import futures
from fnmatch import fnmatch

from protos.chat_pb2 import *
from protos.chat_pb2_grpc import *
from config import DEBUG, LOCALHOST, PUBLIC_STATUS, SERVER_PORT
from entity import User
from utils import get_ipaddr


class ChatServer(ChatServicer):
    """Main server class that manages users and message state for all clients."""

    def __init__(self):
        # Initialize storage for users and messages
        self.users: dict[str, User] = {}
        self.messages: dict[uuid.UUID, Message] = {}
        self.inbound_volume: int = 0
        self.outbound_volume: int = 0

    def Echo(self, request: EchoRequest, context: grpc.ServicerContext) -> EchoResponse:
        return EchoResponse(status=Status.SUCCESS,
                            message=request.message)

    def Authenticate(self, request: AuthRequest, context: grpc.ServicerContext) -> AuthResponse:
        """
        This function handles all authentication requests: users creating an account or logging in.

        The function returns three possible errors to the client:
        1. Attempting to create an account with a username that already exists.
        2. Attempting to log into an account that doesn't exist.
        3. Attempting to log into an account with the wrong password.

        If there was an error, the server sends an ErrorResponse() object with a description to the client.
        On success, the server sends a blank AuthResponse() object to the client.

        :param request: The AuthRequest object.
        :param context: The servicer context.
        :rtype: AuthResponse
        """
        self.inbound_volume += len(request.SerializeToString())

        username, password = request.username, request.password
        match request.action_type:
            case AuthRequest.ActionType.CREATE_ACCOUNT:
                if username in self.users:
                    resp = AuthResponse(status=Status.ERROR,
                                        error_message=f"Create account failed: user \"{username}\" already exists.")
                else:
                    self.users[username] = User(username=username, password=password)
                    resp = AuthResponse(status=Status.SUCCESS)
            case AuthRequest.ActionType.LOGIN:
                if username not in self.users:
                    resp = AuthResponse(status=Status.ERROR,
                                        error_message=f"Login failed: user \"{username}\" does not exist.")
                elif password != self.users[username].password:
                    resp = AuthResponse(status=Status.ERROR,
                                        error_message=f"Login failed: incorrect password.")
                else:
                    resp = AuthResponse(status=Status.SUCCESS)
            case _:
                print("Unknown AuthRequest action type.")
                exit(1)

        self.outbound_volume += len(resp.SerializeToString())

        if DEBUG:
            self.log()

        return resp

    def GetMessages(self, request: GetMessagesRequest, context: grpc.ServicerContext) -> GetMessagesResponse:
        """
        This function handles all get messages requests.

        It responds with a list of non-deleted messages that were sent to the requester.

        :param request: The GetMessagesRequest object.
        :param context: The servicer context.
        :rtype: GetMessagesResponse
        """
        self.inbound_volume += len(request.SerializeToString())

        username = request.username
        assert username in self.users

        # Grab all messages associated with the user
        message_ids = self.users[username].message_ids
        messages = [self.messages[message_id] for message_id in message_ids]

        resp = GetMessagesResponse(status=Status.SUCCESS,
                                   messages=messages)
        self.outbound_volume += len(resp.SerializeToString())

        if DEBUG:
            self.log()

        return resp

    def ListUsers(self, request: ListUsersRequest, context: grpc.ServicerContext) -> ListUsersResponse:
        """
        This function handles all list users requests.

        It responds with a list of all current users whose usernames match the provided wildcard pattern.

        :param request: The ListUsersRequest object.
        :param context: The servicer context.
        :rtype: GetMessagesResponse
        """
        self.inbound_volume += len(request.SerializeToString())

        username, pattern = request.username, request.pattern
        matches = [username for username in self.users if fnmatch(username, pattern)]

        resp = ListUsersResponse(status=Status.SUCCESS,
                                 usernames=matches)
        self.outbound_volume += len(resp.SerializeToString())

        if DEBUG:
            self.log()

        return resp

    def SendMessage(self, request: SendMessageRequest, context: grpc.ServicerContext) -> SendMessageResponse:
        """
        This function handles all send messages requests.

        It inserts the message into the map of message IDs to message objects.
        Then it inserts the message ID into the recipient's message inbox.
        On success, it responds with a blank SendMessageResponse() object.

        :param request: The SendMessageRequest object.
        :param context: The servicer context.
        :rtype: SendMessageResponse
        """
        self.inbound_volume += len(request.SerializeToString())

        username, message = request.username, request.message

        # Assert that the message does not already exist and the request user matches the sender
        assert message.id not in self.messages
        assert username == message.sender

        if message.recipient not in self.users:
            return SendMessageResponse(status=Status.ERROR,
                                       error_message=f"Send message failed: recipient \"{message.recipient}\" does not exist.")

        # Store the message
        message_id = uuid.UUID(bytes=message.id)
        self.messages[message_id] = message

        # Add the message to the recipient's inbox
        recipient = self.users[message.recipient]
        recipient.add_message(message_id)

        resp = SendMessageResponse(status=Status.SUCCESS)
        self.outbound_volume += len(resp.SerializeToString())

        if DEBUG:
            self.log()

        return resp

    def ReadMessages(self, request: ReadMessagesRequest, context: grpc.ServicerContext) -> ReadMessagesResponse:
        """
        This function handles all read messages requests.

        It iterates over a list of message IDs.
        For each message ID, it gets the message object corresponding to the message ID.
        It sets the read flag of the message to true.
        On success, it responds with a blank ReadMessageResponse() object.

        :param request: The ReadMessagesRequest object.
        :param context: The servicer context.
        :rtype: ReadMessagesResponse
        """
        self.inbound_volume += len(request.SerializeToString())

        username, message_ids = request.username, request.message_ids

        # Set the read flag for each message in the request
        for message_id in message_ids:
            # Convert to UUID
            message_id = uuid.UUID(bytes=message_id)
            assert message_id in self.messages

            message = self.messages[message_id]

            # Assert that the recipient matches the request username
            assert message.recipient == username

            # Mark the message as read
            assert not message.read
            message.read = True

        resp = ReadMessagesResponse(status=Status.SUCCESS)
        self.outbound_volume += len(resp.SerializeToString())

        if DEBUG:
            self.log()

        return resp

    def DeleteMessages(self, request: DeleteMessagesRequest, context: grpc.ServicerContext) -> DeleteMessagesResponse:
        """
        This function handles all delete messages requests.

        It iterates over a list of message IDs.
        For each message ID, it gets the message object corresponding to the message ID.
        It deletes the message object as well as the ID from the recipient's inbox.
        On success, it responds with a blank DeleteMessagesResponse() object.

        :param request: The DeleteMessagesRequest object.
        :param context: The servicer context.
        :rtype: DeleteMessagesResponse
        """
        self.inbound_volume += len(request.SerializeToString())

        username, message_ids = request.username, request.message_ids

        # Get the recipient
        recipient = self.users[username]

        # Delete the messages one by one
        for message_id in message_ids:
            # Convert to UUID
            message_id = uuid.UUID(bytes=message_id)
            assert message_id in self.messages

            # Get the message to delete
            message = self.messages[message_id]

            # Assert that the recipient matches the request username
            assert message.recipient == username

            # Delete the message from the recipient
            recipient.delete_message(message_id)

            # Delete the message
            del self.messages[message_id]

        resp = DeleteMessagesResponse(status=Status.SUCCESS)
        self.outbound_volume += len(resp.SerializeToString())

        if DEBUG:
            self.log()

        return resp

    def DeleteUser(self, request: DeleteUserRequest, context: grpc.ServicerContext) -> DeleteUserResponse:
        """
        This function handles all delete user requests.

        It iterates over the list of message IDs in the deleted user's inbox.
        For each message ID, it erases the corresponding message object.
        The user is then removed from the server's state.
        On success, it responds with a blank DeleteUserResponse() object.

        :param request: The DeleteUserRequest object.
        :param context: The servicer context.
        :rtype: DeleteUserResponse
        """
        self.inbound_volume += len(request.SerializeToString())

        username = request.username

        # Get the user
        assert username in self.users
        user = self.users[username]

        # Delete all messages sent to that user
        for message_id in user.message_ids:
            assert message_id in self.messages
            del self.messages[message_id]

        # Delete the user
        del self.users[username]

        resp = DeleteUserResponse(status=Status.SUCCESS)
        self.outbound_volume += len(resp.SerializeToString())

        if DEBUG:
            self.log()

        return resp

    def log(self):
        """Utility function that logs the state of the server."""
        print("\n-------------------------------- SERVER STATE --------------------------------")
        print(f"USERS: {self.users}")
        print(f"MESSAGES: {self.messages}")
        print(f"TOTAL TRAFFIC (INBOUND): {self.inbound_volume} bytes")
        print(f"TOTAL TRAFFIC (OUTBOUND): {self.outbound_volume} bytes")
        print("------------------------------------------------------------------------------\n")


def main():
    # Initialize the server
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=1))
    add_ChatServicer_to_server(ChatServer(), server)

    # Check for public visibility
    if not PUBLIC_STATUS:
        host = LOCALHOST
    else:
        host = get_ipaddr()
        if host is None:
            print("Error: server IP address could not be found.")
            exit(1)

    # Bind the server to host:port
    server_addr = f"{host}:{SERVER_PORT}"
    server.add_insecure_port(server_addr)
    server.start()

    print(f"Server listening on {server_addr}")
    server.wait_for_termination()
    server.log()


if __name__ == "__main__":
    main()
