# Engineering Notebook: Replication Design Exercise

> [!NOTE]
> **Authors:** Daniel Li, Rajiv Swamy
>
> **Date:** 3/26/25

## 3/16

Idea: use 3 servers

- Primary-based write replication: coordinator will wait for all replicas to respond.
- Since there are only 3 servers, this should be manageable.

We need to address leader election first.
The Garcia-Molina [**Bully Algorithm**](https://en.wikipedia.org/wiki/Bully_algorithm) seems promising.

- The algorithm assumes that all servers have unique IDs and know about each other's IDs.
- The goal is to elect the online server with the greatest ID as the leader.
- Followers use periodic heartbeats to determine when the leader has gone down.

#### Pros

- Relatively simple to implement.
- Seems quite robust with a relatively consistent convergence speed.
- Quite adaptable to adding more servers.

#### Cons

- Need mutexes to avoid race conditions.
- There are times when a server has no leader (waiting on a coordinator request).

## 3/17

### Chat Server Skeleton

```protobuf
service Chat {
    // Called by the new leader to announce itself as coordinator
    rpc Coordinator(CoordinatorRequest) returns (Ack);

    // Called when a server starts an election
    rpc Election(ElectionRequest) returns (Ack);

    // Called periodically to check if a server is alive
    rpc Heartbeat(HeartbeatRequest) returns (Ack);
}
```

This is a basic chat service skeleton that the bully algorithm uses.
Servers use `chat.Election` to start an election.
Newly elected leaders announce themselves with `chat.Coordinator`.
Heartbeats are sent with the `chat.Heartbeat` RPC.
Each server will maintain a heartbeat thread to determine whether the leader has gone down.
Once this is detected, a new election will be triggered.

The bully algorithm prototype seems to be working!
The main goal today is to figure out how to cleanly integrate it with an existing service.

The problem is that the leader can crash in the middle of executing a request

- For example, a server forwards a request to the leader (a send message request).
- The leader is in the process of propagating this change to the other followers.
- However, the leader crashes sometime in the middle.
- A new leader is elected but this leader must now replay those changes.

What is _supposed_ to happen? Let's assume for a moment that there are no crashes.
One leader, two followers, all is working as normal.

- The leader gets some query.
- It executes the query and writes the query to its log.
- It _commits_ both of these changes atomically.
- It forwards the query to all followers and waits for a response/timeout.
- It then acknowledges the query back to the client.

## The Commit Log

The key is the commit log.
Essentially an entire history from which the state of the server can be rebuilt.

Writes to the commit log _must_ be atomic.
Any write to the commit log either executes successfully or does not execute at all.
Otherwise, we would fail to rebuild the state of the application from the commit log.

## The Concept of a Commit

Fundamentally, a commit should consist of two things:

- An integer timestamp (similar to a Lamport timestamp).
- The request. This is some query that alters the state of the application.

To make things simple, we should just use JSON-strings for all requests from now on.
This will make it really easy to persist commits.

```protobuf
message Commit {
    int32 id = 1;           // ID of the commit
    string request = 2;     // The request (JSON-string)
}
```

## 3/18

- Even with commit logs, there can be moments where the logs don't match up.
- Need to come up with a way to synchronize the commit logs, this is difficult!
- The key lies in how we elect a new leader.
- We should always elect the leader with the LATEST commit.
- To determine latest, we can just look at the timestamp of the latest commit.

...

It turns out that this just leads to a broadcast storm of elections.
The reason being that the broadcast graph is no longer a DAG.

- _Prior_ to sending an election request, the servers do not know who has higher priority.
- This means server 1 sends to server 2, which causes server 2 to send election requests...
- Eventually this chain gets back to server 1, which starts another election...
- So elections would trigger more elections...

The very act of sending a message must be directed.
The example above suggests that this directed graph must form a DAG.
There are ways to get around this, we can tag the elections with a sequence number.

To keep things simple, we will just use the bully algorithm and find other ways to sync commit logs.

- We need to guarantee that the servers stay _consistent_ at all times
- Server 1 and server 2 must not have a _different_ commit $i$ for some $i$.
- If this happens then all bets are off... a corrupted history is hard to recover from.

### Commit Log Synchronization

The leader needs to ensure that the replicas stay consistent.
How do we do this?

The idea is that once a new leader is elected, it will request the replicas for new commits.

```protobuf
message GetCommitsRequest {
    int32 server_id = 1;            // ID of the requester
    int32 latest_commit_id = 2;     // Fetch all commits occurring after this one
}

message GetCommitsResponse {
    repeated Commit commits = 1;    // The commits requested
}
```

Once a new leader has been elected, it will broadcast a coordinator request.
This contains its own commit history.
From this commit history, any outdated replicas can catch up to the new changes.

```protobuf
message CoordinatorRequest {
    int32 leader_id = 1;                    // ID of the new leader
    repeated Commit commit_history = 2;     // The commit history of the new leader
}
```

## 3/19

- Decided on using SQLite for persistent storage.
- Simple to use and supports transactions with `db.commit()`.

### Who Should be Forwarding?

There are options here.
What's done in practice is that the client will send a request to the leader.

Of course, the client doesn't know who the leader is, so there is some middleman (load balancer).
This middleman also needs to be fault-tolerant, so the middleman itself is a set of some servers.

Once the request gets to the leader, the leader will send the request to all the replicas.
Once a majority of the replicas have responded, the leader sends a response back to the client.

This ensures the following:

1. The client only sends one request.
2. The client does not wait too long (only wait for a majority).

In our example:

- The number of servers is small (3).
- Each operation is quite fast (usually a single database read/write).

For convenience of implementation, we have the client send the request to all three servers.
The last successful response that it gets is the response that it will use.
This means that if a server is offline, it skips the server.

This makes request forwarding a lot simpler, the leader does not need to coordinate other replicas.
The only thing the leader needs to do is ensure that all replicas stay consistent by:

- Requesting for new commits.
- Sending its commit history so outdated replicas can catch up.

## 3/20

### Commit Log Implementation

```sqlite
CREATE TABLE IF NOT EXISTS commits
(
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    request TEXT NOT NULL
)
```

Every time a server gets a request that modifies state, it will:

- Execute the request.
- Create a new commit and insert the commit into the commits table.
- Commit everything at once, fulfilling the transaction.

### Application Data Persistent Storage

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

#### Users Table

```sqlite
CREATE TABLE IF NOT EXISTS users
(
    username TEXT PRIMARY KEY,
    password TEXT NOT NULL
)
```

## 3/21

Updating the GUI should be quite straightforward.

Since the client is now making requests to all servers, we should have a request wrapper.

### Request Wrapper

```python
def send_request(request, server_ip):
    id_to_addr = get_id_to_addr_map(server_ip)

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

        except grpc.RpcError as e:
            # Handle error
            pass

        finally:
            if channel is not None:
                channel.close()

    return response
```

Individual API endpoints are now defined in the `api` package.
These endpoints are built on top of the request wrapper.

### Testing

Testing is done with PyTest.

#### Main Test Suite

The main test suite tests the following.

- Creating a user
    - Test that username collisions are handled.
- Logging in
    - Test for nonexistent users.
- Get messages
    - Asserting that sent messages are being received.
    - Asserting that messages are returned in chronological order.
    - Test fetching for a nonexistent user.
- Send Messages
    - Test that messages are getting delivered.
    - Test sending to a nonexistent user.
- List users
    - Test that the glob pattern matching works.
    - Testing for no matches.
    - Testing for some matches.
    - Testing for all matches (*).
- Reading messages
    - Read a list of messages for a user.
    - Fetch messages for that user.
    - Assert that the `read` attribute should now be set to true.
- Deleting messages
    - Delete a set of messages for a user.
    - Fetch messages for that user.
    - Assert messages are gone.
- Deleting users
    - Delete a user.
    - Assert that the user does not show up in a `list_users(*)` query.
    - Assert that fetching messages for that user now returns null.
    - Assert that sending a message for that user returns a `"Recipient does not exist."` error.

#### Testing Persistence

The idea is to reuse our main test suite but stagger the test cases.
This means we should shut the servers down and restart the servers in between test cases.
The only way the test cases still pass is if the state is being persisted.

## 3/22

#### Testing Fault Tolerance

The idea is simple:

- Send a request.
- Stop some of the servers.
- Send more requests.
- Restart/stop some more servers.

Ideally, the requests should depend on each other to truly test fault tolerance.

We can use a PyTest fixture to facilitate testing fault tolerance.

#### Server Manager

```python
class ServerManager:
    """Encapsulates starting/stopping servers for more direct usage in tests."""

    def __init__(self):
        # ID to server process
        self.procs: dict[int, subprocess.Popen] = {}

    def start(self, server_id: int):
        # Starts the server with a specific ID
        pass

    def stop(self, server_id: int):
        # Ends the server with a specific ID
        pass

    def start_all(self):
        # Starts all servers
        pass

    def stop_all(self):
        # Stops all servers
        pass


@pytest.fixture
def server_manager():
    """Pytest fixture that starts all servers and allows control during test."""
    # Create server manager and start all the servers
    manager = ServerManager()
    manager.start_all()

    # Yield the manager to the test case
    yield manager

    # Stop the servers
    manager.stop_all()
```

Now we can stop servers and restart servers on the fly.
