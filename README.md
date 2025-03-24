# CS 2620: Replication Design Exercise

> [!NOTE]
> **Authors:** Daniel Li, Rajiv Swamy
>
> **Date:** 3/26/25

## Usage Instructions

This app is built in Python. To run the server and the client, follow the steps below.

1. Install the python packages in a virtual environment:
    ```shell
    > python3 -m venv venv
    > source venv/bin/activate
    > pip install -r requirements.txt
    ```
2. Change config settings in `config/config.yaml`
    - If you would like to run the client and the server on different computers, set `network.public_status` to
      `true`.
    - Ensure the client and the server computers are on the same local network.
    - The IP addresses and ports of the servers must be specified in the configuration file.
        - See `id_to_addr_local` and `id_to_addr_public`.
        - Set the IP address and port of each server to the corresponding server ID.
    - For example, if you want server 1 to run on `10.0.0.1:50000`, set `ip_to_addr_local.1` to `"10.0.0.1:50000"`.
    - If you are running the client and server locally,
3. Open a terminal and run the server with: `python server.py --id $ID`
    - `ID` is the ID of the server you wish to start.
4. Run the client: `python client.py`.

### Replication

To run a replicated server, you can start three servers.
Suppose that you wish to replicate on two machines with IP addresses `10.0.0.1` and `10.0.0.2`, respectively.

A configuration that replicates servers 1 and 2 on machine 1 and server 3 on machine 2 can be specified as follows.

```yaml
id_to_addr_public:
    1: "10.0.0.1:60001"
    2: "10.0.0.1:60002"
    3: "10.0.0.2:60003"
```

Then, on machine 1, run `python server.py --id 1` and `python server.py --id 2` in two separate terminals.
On machine 2, run `python server.py --id 3`.

### Clearing the State

Clearing the state of the application can be toggled on startup: running `python server.py --id 1 --reset` will start
the first server but clear its database file.

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
    // Called by the new leader to announce itself as coordinator
    rpc Coordinator(CoordinatorRequest) returns (Ack);

    // Called when a server starts an election
    rpc Election(ElectionRequest) returns (Ack);

    // Executes a query
    rpc Execute(ExecuteRequest) returns (ExecuteResponse);

    // Gets all commits after a specified commit ID
    rpc GetCommits(GetCommitsRequest) returns (GetCommitsResponse);

    // Called periodically to check if a server is alive
    rpc Heartbeat(HeartbeatRequest) returns (Ack);
}
```

This interface significantly changes from design exercise 2.
The service now primarily interfaces with the servers, not the client.
Specifically, we did not want to mix application endpoints (for implementing the chat server) with endpoints that
implement backend details like leader election, commit log synchronization.

All client requests are routed to the `Execute()` endpoint. The request will be given in the form of a JSON-string.

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

## Backend Approach

The backend of our app is implemented in the `server.py` file.
We used **SQLite** for our persistent storage solution and to facilitate replication.

### Query Execution

As we'll see, all state manipulations required of this chat application can be implemented with database operations.

### Persistent Storage

For application data, all we really need are two tables: one for messages and one for users.
Every operation can be correctly implemented with these two tables.

- Getting all messages for a user
    - This can be done with a SQLite query.
    - Select all messages where the recipient matches the username.
    - This is a read operation and does not need a commit.
- Listing all users that match a glob pattern
    - SQLite select query with `GLOB`.
    - Read operation -- does not need a commit.
- Sending a message
    - Insert the new message into the table.
    - This operation is a database write (which changes state) and needs a commit.
- Reading a set of messages
    - Update all messages (set `read = 1`) where the ID is in a list of message IDs.
    - Write operation -- needs a commit.
- Deleting a set of messages
    - Delete all messages where the ID is in a list of message IDs.
    - Write operation -- needs a commit.
- Deleting a user
    - Delete the user from the users table.
    - Delete all messages where the recipient is the user.
    - Write operation -- needs a commit.

#### Messages Table

```sqlite
CREATE TABLE IF NOT EXISTS messages
(
    id        TEXT PRIMARY KEY,
    sender    TEXT    NOT NULL,
    recipient TEXT    NOT NULL,
    body      TEXT    NOT NULL,
    timestamp REAL    NOT NULL,
    read      BOOLEAN NOT NULL DEFAULT 0
);
```

The primary key `id` for messages is generated with Python's `uuid.uuid4()` and converted to a raw string.

#### Users Table

```sqlite
CREATE TABLE IF NOT EXISTS users
(
    username TEXT PRIMARY KEY,
    password TEXT NOT NULL
)
```

The password is hashed on the client-side with Python's `hashlib.sha256()` and stored in the database.

### Sending Messages

Our implementation does not allow a user to view the history of the messages they have sent.
This was a decision that was made because the assignment specifications and discussions with the course staff have made
it clear that only the user who _receives_ a message can delete it. To simplify our implementation, we have made it so
that once a message is sent, the sender no longer has any association with the message.

### Deleting a User

As for the project specifications, we must specify what happens to unread messages on a **delete user request.**
Our implementation will delete all the user's received messages regardless of whether they are unread or not.

## Testing

All test cases are provided in one test suite.
This file builds on the integration test from the previous assignment.

To run the tests:

1. Open a terminal and activate the virtual environment: `source venv/bin/activate`.
2. Run the tests: `pytest tests`.

#### Main Test Suite

The main test suite is described in `notebook.md`.
Essentially, it tests all the API endpoints (the core functionality of the chat application) are functional.
It also tests common edge cases.

#### Testing Persistence

The idea is to reuse our main test suite but stagger the test cases.
This means we should shut the servers down and restart the servers in between test cases.
The only way the test cases still pass is if the state is being persisted.

#### Testing Fault Tolerance

The idea is simple:

- Send a request.
- Stop some of the servers.
- Send more requests.
- Restart/stop some more servers.

Ideally, the requests should depend on each other to truly test fault tolerance.
We used a PyTest fixture to facilitate testing fault tolerance.
