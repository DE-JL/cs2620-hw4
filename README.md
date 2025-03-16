# CS 2620: Wire Protocols Design Exercise

> [!NOTE]
> **Authors:** Daniel Li, Rajiv Swamy
>
> **Date:** 2/12/25

## Usage Instructions

This app is built in Python. To run the server and UI Client, do the following:

1. Install the python packages in a virtual environment:
    - `python3 -m venv venv`
    - `source venv/bin/activate`
    - `pip install -r requirements.txt`
2. Change config settings in `config/config.yaml`
    - If you would like to run the client UI and the server on separate computers, set `network.public_status` to
      `true`.
    - Ensure the client and the server computers are on the same local network. On startup, the server will print its IP
      address and port.
    - To toggle the wire protocol implementation between JSON and custom, set `protocol_type` to `json` or `custom`.
3. Open a terminal and run the server: `python server.py`
    - If you'd like to run the client UI and the server on separate computers, note the host name and port name in the
      console output from running the server application.
4. Run the client: `python client_ui.py [host] [port]`

## RPC

For the RPC, we decided to use Google’s gRPC framework with Protocol Buffers (protobuf) as the IDL. This was primarily
because Python applications written with gRPC and protobuf are well-documented and easy to learn.

### Protocol Buffers Compilation

To generate the Python code, we can compile our `chat.proto` file as follows:

```
python -m grpc_tools.protoc \
   -I=. \
   --python_out=. \
   --pyi_out=. \
   --grpc_python_out=. \
   protos/chat.proto
```

This will generate files:
- `chat_pb2.py`: classes for the message types defined in the proto file
- `chat_pb2.pyi`: type hints for IDEs
- `chat_pb2_grpc.py`: the servicer and stub classes

### Service Interface

Our chat service defines the interface available to the client.

```protobuf
service Chat {
    rpc Echo(EchoRequest) returns (EchoResponse) {}

    rpc Authenticate(AuthRequest) returns (AuthResponse) {}

    rpc GetMessages(GetMessagesRequest) returns (GetMessagesResponse) {}

    rpc ListUsers(ListUsersRequest) returns (ListUsersResponse) {}

    rpc SendMessage(SendMessageRequest) returns (SendMessageResponse) {}

    rpc ReadMessages(ReadMessagesRequest) returns (ReadMessagesResponse) {}

    rpc DeleteMessages(DeleteMessagesRequest) returns (DeleteMessagesResponse) {}

    rpc DeleteUser(DeleteUserRequest) returns (DeleteUserResponse) {}
}
```

This interface did not change much at all compared to the first design exercise: this is because we organized our server
implementation in a similar fashion—it was easy to translate our interface to gRPC style.

### Data Classes

The non-trivial type sent between the client and the server is the Message type. This holds all the data required to
represent one unique message sent between users.

```protobuf
message Message {
    bytes id = 1;
    string sender = 2;
    string recipient = 3;
    string body = 4;
    double timestamp = 5;
    bool read = 6;
}
```

Note that because protobuf does not have a native UUID type, we are using `bytes` objects to hold the raw bytes for a
UUID. To retrieve the actual UUID for hashing, we can convert from bytes to UUID with `uuid.UUID(bytes=bytes)` and UUID
to bytes with `uuid.bytes`.

All the other request types and response types not containing the `Message` type can be represented with protobuf native
types (most are strings).

## Project Structure

Our project structure mirrored that of the first design exercise: one file for the server that implements all the server
logic and another file for the client UI implementation. We put all the protobuf definitions in a file called
`protos/chat.proto` and generated the Python message class files and server/stub files in the `protos/` directory.

## Frontend Approach

The frontend of our app is built with the PyQt library. PyQt was chosen as it fit the class language constraints and had
extensive support and documentation. Once the user runs the terminal command to open the UI, they will be presented with
a screen to log in or create a new account. When the user runs this command, the app will immediately spin up a socket
connection with the server through a `UserSession` object. Once authenticated the user will be taken to the main frame
of the app, where they can sign out, delete their account, send a message, search existing accounts, and view their
messages.

Our app takes an HTTP-esque approach in retrieving and modifying user data. The frontend is responsible for retrieving
new state and sending modifications to the server (i.e., hence our API corresponds to relevant GET, PUT, POST, and
DELETE requests for the corresponding user and message entities). Because of this design, we designed the frontend to
recurrently make GetMessage requests to the server by using a `MessageUpdaterWorker` on a separate thread (this worker
uses a different socket connection) and makes modifications to the view messages screen accordingly. When the user reads
a message or deletes a message, the client sends `read` and `delete` requests to the server respectively. After the
server updates the state, the frontend `MessageUpdaterWorker` will update the messages state on the client and emit a
signal that tells the UI to update the view messages screen.

### Updates with Design Exercise 2

When switching from our custom protocol to gRPC, we needed to refactor the frontend code to make requests to the gRPC
channel using the parser host and post arguments with the stub. These changes were pretty straightforward to make as our
requests and models remain unchanged.

## Backend Approach

The backend of our app is implemented in the `server.py` file. The server spins up one socket to handle requests from
multiple clients using the selector approach discussed in class. The user and message data persists in memory currently.
When the user wants to spin up a client on a public computer (the `public_status` flag is set to `true`), the server
will provide descriptive output of the host and port to connect to for the client. All request handlers were implemented
in `server.py`.

### Execution

Since we are not persisting chat information to disk, all information regarding users and messages is stored in memory
by the server.

```py
class ChatServer(ChatServicer):
    """Main server class that manages users and message state for all clients."""

    def __init__(self):
        # Initialize storage for users and messages
        self.users: dict[str, User] = {}
        self.messages: dict[uuid.UUID, Message] = {}
        self.inbound_volume: int = 0
        self.outbound_volume: int = 0
```

The `ChatServer` class inherits from `ChatServicer`, which is defined in the generated `protos/chat_pb2_grpc.py` file.

Users are identified by their unique alphanumeric username.
Messages are identified by a 16-byte UUID that is assigned on the _client_ side.
These two dictionaries comprise all the data stored by our server at any given time.

#### Request Handling

For request handling, we override the methods implemented by the default CherServicer class to update the users,
messages state accordingly and return the corresponding response objects.

#### Sending Messages

Our implementation does not allow a user to view the history of the messages they have sent.
This was a decision that was made because the assignment specifications and discussions with the course staff have made
it clear that only the user who _receives_ a message can delete it. To simplify our implementation, we have made it so
that once a message is sent, the sender no longer has any association with the message.

#### Deleting a User

As for the project specifications, we must specify what happens to unread messages on a **delete user request.**
Our implementation will delete all the user's received messages regardless of whether they are unread or not.

## Testing

Integration tests are provided. This file builds on the integration test from the previous assignment. This time, we
didn’t have to stress test our own wire protocol.

To run the tests:

1. Open a terminal and activate the virtual environment: `source venv/bin/activate`.
2. Run the tests: `python -m pytest tests/`.

### Integration Tests

Integration tests were done in `tests/test_integration.py`.
In these test results, a client-server connection was established, and requests were sent over to the server over the
network instead of calling the request handlers manually.
