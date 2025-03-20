import argparse
import json
import os
import sqlite3
import threading
import time

from concurrent import futures

from protos.chat_pb2 import *
from protos.chat_pb2_grpc import *
from utils import get_id_to_addr_map


class ChatServer(ChatServicer):
    """Server implementation."""

    HEARTBEAT_INTERVAL = 2
    ELECTION_TIMEOUT = 2

    def __init__(self, server_id: int):
        """
        Represents a server instance in a distributed system that manages communication,
        concurrency, and leader election processes. It provides initialization to set
        up server attributes, lock mechanism for thread safety, and starts a background
        thread for sending heartbeat signals.

        :param server_id: Unique identifier for the server.
        """
        self.server_id = server_id
        self.id_to_addr = get_id_to_addr_map()

        # Initialize the database
        self.db_file = f"db/server{self.server_id}.db"
        os.makedirs("db", exist_ok=True)
        self.init_db()

        # Storage of request IDs for uniqueness
        self.request_ids = self.get_request_ids()

        # Initially, we don’t know the leader yet
        self.leader_id = None

        # For concurrency control
        self.lock = threading.Lock()

        # Synchronize the state
        self.synchronize_commits()

        # Start background heartbeat thread
        self.shutdown = threading.Event()
        self.election_in_progress = False

        # Start the heartbeat monitor
        self.heartbeat_thread = threading.Thread(target=self.send_heartbeats,
                                                 daemon=True)
        self.heartbeat_thread.start()

    def Coordinator(self,
                    request: CoordinatorRequest,
                    context: grpc.ServicerContext) -> Ack:
        """
        Processes a request to acknowledge a new leader.

        This method is invoked when another server proposes a leader ID that must be greater
        than the current server's ID. The function ensures a thread-safe operation to update
        the current leader ID using a lock, and then acknowledges the new leader proposal.

        :param request: The coordinator request containing the proposed leader ID.
        :param context: The context object.
        :return: Acknowledgment message confirming the new leader is recorded.
        """
        assert request.leader_id > self.server_id, "Leader ID must be larger than our own ID."

        # Acquire the lock to set the leader ID
        with self.lock:
            # Apply any new commits
            latest_commit_id = self.get_latest_commit_id()
            commit_history = list(request.commit_history)

            # Get the new commits
            new_commits = [commit for commit in commit_history if commit.id > latest_commit_id]
            self.apply_commits(new_commits)

            # Set new leader
            self.leader_id = request.leader_id

            print(f"[Server {self.server_id}] Acknowledging new leader: server {self.leader_id}")

        return Ack()

    def GetCommits(self,
                   request: GetCommitsRequest,
                   context: grpc.ServicerContext) -> GetCommitsResponse:
        """
        Handles the retrieval of commits based on the request provided. This method
        processes the `GetCommitsRequest`, accesses the required resources, and returns
        a `GetCommitsResponse` containing the details of the commits requested.

        :param context: The get commits request.
        :param request: The gRPC context object.
        """
        print(f"[Server {self.server_id}] Received get commits request from server {request.server_id}")

        with self.lock:
            with sqlite3.connect(self.db_file) as db:
                cursor = db.execute("SELECT id, query FROM commits WHERE id > ? ORDER BY id",
                                    (request.latest_commit_id,))
                rows = cursor.fetchall()

        # Construct the commits list
        commits = [Commit(row[0], row[1]) for row in rows]
        return GetCommitsResponse(commits=commits)

    def Election(self,
                 request: ElectionRequest,
                 context: grpc.ServicerContext) -> Ack:
        """
        Handles the initiation of a leader election process among distributed servers.

        This function is invoked to trigger a leader election in a distributed system
        when a node with a lower ID requests for one. The election logic is
        executed in a separate thread to ensure the gRPC server remains responsive.
        The method returns an acknowledgment upon successful initiation of the
        election process.

        :param request: The election request containing the candidate ID.
        :param context: The gRPC context object.
        :return: An acknowledgment that the election request has been received.
        """
        print(f"[Server {self.server_id}] Received election request from server {request.candidate_id}")
        assert request.candidate_id < self.server_id, "Candidate ID must be smaller than our ID."

        # Trigger an election start
        t = threading.Thread(target=self.start_election,
                             daemon=True)
        t.start()

        return Ack()

    def Execute(self,
                request: ExecuteRequest,
                context: grpc.ServicerContext) -> ExecuteResponse:
        """
        Processes an Execute request in a gRPC server and provides an acknowledgment response.
        This function serves as a core component to handle execution requests, process the
        necessary logic, and return a corresponding acknowledgment.

        :param request: The execution request containing the query.
        :param context: The gRPC context object.
        :return: The response
        """
        print(f"[Server {self.server_id}] received request {request.request}")

        with self.lock:
            response = self.execute_request(request.request)

        return ExecuteResponse(response=response)

    def Heartbeat(self,
                  request: HeartbeatRequest,
                  context: grpc.ServicerContext) -> Ack:
        """
        Handles the heartbeat communication between the client and the server.
        This method is invoked to ensure that the client-server connection
        remains active and responsive. It processes the heartbeat request
        from the client and returns an acknowledgment to confirm the connection
        status.

        :param request: The heartbeat request.
        :param context: The gRPC context object.
        :return: An acknowledgment that the heartbeat was received.
        """
        return Ack()

    def stop(self):
        """Stop the heartbeat thread gracefully."""
        self.shutdown.set()
        self.heartbeat_thread.join()

    def send_heartbeats(self):
        """Periodically check if the leader is alive. If not, start an election."""
        while not self.shutdown.is_set():
            # Get the leader ID
            with self.lock:
                leader_id = self.leader_id

            # No leader -> start election
            if leader_id is None:
                self.start_election()
            elif leader_id != self.server_id:
                try:
                    # We have a known leader, check if it's alive
                    assert isinstance(leader_id, int)
                    addr = self.id_to_addr[leader_id]

                    # Make the RPC
                    channel = grpc.insecure_channel(addr)
                    stub = ChatStub(channel)
                    stub.Heartbeat(HeartbeatRequest(server_id=self.server_id))
                except grpc.RpcError as _:
                    print(f"[Server {self.server_id}] Detected leader {self.leader_id} is unresponsive")
                    with self.lock:
                        self.leader_id = None

            time.sleep(self.HEARTBEAT_INTERVAL)

    def start_election(self):
        """
        Bully Algorithm approach:
        1. Send an election request to all peers.
        2. If none reject, then we become the leader.
        3. If at least one accepts, then we are good to go.
        """
        # Check if an election is already in progress
        with self.lock:
            if self.election_in_progress:
                return

            # Clear the leader and start the election
            self.leader_id = None
            self.election_in_progress = True

        print(f"[Server {self.server_id}] Initiating election...")

        # Track if any peer with greater ID accepted our request
        election_accepted = True

        # Send election requests
        for peer_id, addr in self.id_to_addr.items():
            if peer_id <= self.server_id:
                continue
            try:
                # Build stub
                channel = grpc.insecure_channel(addr)
                stub = ChatStub(channel)

                # Send the request
                request = ElectionRequest(candidate_id=self.server_id)
                stub.Election(request=request,
                              timeout=self.ELECTION_TIMEOUT)

                # If they responded, then we will NOT be the new leader
                election_accepted = False
            except grpc.RpcError as _:
                print(f"[Server {self.server_id}] Election request to {peer_id} failed to send")

        # If no server rejected our request, then we become the new leader
        if election_accepted:
            with self.lock:
                # Synchronize commit history with the other peers
                self.synchronize_commits()

                # Broadcast new coordinator
                self.broadcast_coordinator()

                # Set new leader
                self.leader_id = self.server_id
                self.election_in_progress = False

            print(f"[Server {self.server_id}] Elected server {self.leader_id} as leader.")
        else:
            # Just wait for a coordinator request
            with self.lock:
                self.election_in_progress = False

    def init_db(self):
        """
        Initializes the database for the server by connecting and setting up required tables.

        The method connects to a SQLite database file specific to the server instance,
        with the file name based on the server id, and initializes tables for handling
        commits, messages, and users. It ensures the tables are created if they do not
        exist already and commits any changes to the database.
        """
        # Connect to the DB for this server
        with sqlite3.connect(self.db_file) as db:
            # Create the write-ahead log table
            db.execute("""
                CREATE TABLE IF NOT EXISTS commits (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    request TEXT NOT NULL
                )
            """)

            # Create the messages table
            db.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    sender TEXT NOT NULL,
                    recipient TEXT NOT NULL,
                    body TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    read BOOLEAN NOT NULL DEFAULT 0
                );
            """)

            # Create the users table
            db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    username TEXT PRIMARY KEY,
                    password TEXT NOT NULL
                )
            """)

            # Commit the changes.
            db.commit()

    def synchronize_commits(self):
        """
        Synchronizes the commit records between the current server and its peer servers. For each peer
        server, this function collects commits that occurred strictly after the local `latest_commit_id`
        value. It then applies those commits to the local database. This ensures the local database
        reflects the state of the distributed system's other nodes.
        """
        for peer_id, addr in self.id_to_addr.items():
            if peer_id == self.server_id:
                continue
            try:
                # Create stub
                channel = grpc.insecure_channel(addr)
                stub = ChatStub(channel)

                # Retrieves all commits occurring strictly after `latest_commit_id`
                request = GetCommitsRequest(server_id=self.server_id,
                                            latest_commit_id=self.get_latest_commit_id())
                response: GetCommitsResponse = stub.GetCommits(request)

                # Apply all the commits
                self.apply_commits(list(response.commits))
            except grpc.RpcError as _:
                pass

        print(f"[Server {self.server_id}] Synchronized commit history with peers")

    def broadcast_coordinator(self):
        """
        Broadcasts the coordinator announcement to all peers in the network,
        except the server itself. A gRPC channel is created for each peer,
        and a CoordinatorRequest is sent to notify them about the current
        leader and empty commit state.

        :param self: An instance of the class containing necessary information
                     about server ID and peer addresses.

        :raises grpc.RpcError: Exception occurs during the gRPC communication.
        :return: None
        """
        commits = self.get_all_commits()

        for peer_id, addr in self.id_to_addr.items():
            if peer_id == self.server_id:
                continue
            try:
                # Create stub
                channel = grpc.insecure_channel(addr)
                stub = ChatStub(channel)

                # Announce coordinator
                stub.Coordinator(CoordinatorRequest(leader_id=self.server_id,
                                                    commit_history=commits))
                print(f"[Server {self.server_id}] Sent coordinator announcement to {peer_id}")
            except grpc.RpcError as _:
                pass

    def get_all_commits(self) -> list[Commit]:
        """
        Returns all rows from the commits table, sorted by their primary key (id).

        :return: A list of `Commit` objects, sorted by ID.
        """
        with sqlite3.connect(self.db_file) as db:
            cursor = db.execute("SELECT id, request FROM commits ORDER BY id")
            rows = cursor.fetchall()

        return [Commit(id=row[0], request=row[1]) for row in rows]

    def get_latest_commit_id(self) -> int:
        """
        Retrieves the latest commit ID from the database.

        This method connects to the SQLite database defined by the given `db_file`.
        It executes a query to determine the maximum value of the `id` field in the
        `commits` table, which corresponds to the latest commit ID. If there are
        no commits in the database, the method returns 0. Otherwise, it returns
        the maximum commit ID.

        :return: The latest commit ID from the database, or 0 if there are no commits present.
        """
        with sqlite3.connect(self.db_file) as db:
            cursor = db.execute("SELECT MAX(id) FROM commits")
            result = cursor.fetchone()

        return 0 if result[0] is None else result[0]

    def apply_commits(self, commits: list[Commit]):
        """
        Applies a list of commits to the SQLite database.

        This method takes a list of `Commit` objects and applies each commit by inserting
        its details into the database and executing the associated SQL query. Once all commits
        are successfully executed, the changes are committed to the database.

        :param commits: A list of commits to apply
        """
        for commit in commits:
            self.execute_request(commit.request)

    def get_request_ids(self) -> set[str]:
        """
        Retrieve the set of unique request IDs from the commits table.

        :return: A set of (string) IDs.
        """
        with sqlite3.connect(self.db_file) as db:
            cursor = db.execute("SELECT request FROM commits")
            rows = cursor.fetchall()

        request_ids = set()
        for row in rows:
            request = json.loads(row[0])
            request_ids.add(request["id"])

        return request_ids

    def execute_request(self, request: str) -> str:
        # Convert the request to a JSON object
        request = json.loads(request)

        # Check for duplicate IDs
        if request["id"] in self.request_ids:
            return ""

        # Forward the request to the right handler
        match request["request_type"]:
            case "AUTH":
                response = self.handle_auth(request)
            case "GET_MESSAGES":
                response = self.handle_get_messages(request)
            case "LIST_USERS":
                response = self.handle_list_users(request)
            case "SEND_MESSAGE":
                response = self.handle_send_message(request)
            case "READ_MESSAGES":
                response = self.handle_read_messages(request)
            case "DELETE_MESSAGES":
                response = self.handle_delete_messages(request)
            case "DELETE_USER":
                response = self.handle_delete_user(request)
            case _:
                raise ValueError("Invalid request type.")

        # Remember the ID
        self.request_ids.add(request["id"])

        return json.dumps(response)

    def handle_auth(self, request: dict) -> dict:
        assert request["request_type"] == "AUTH"

        # Grab username and password
        username = request["username"]
        password = request["password"]

        if request["action_type"] == "CREATE_USER":
            with sqlite3.connect(self.db_file) as db:
                # First check whether the user already exists
                cursor = db.execute("SELECT username FROM users WHERE username = ?",
                                    (request["username"],))
                if cursor.fetchone() is not None:
                    return self.create_error("Username already exists.")

                # Create the user
                db.execute("INSERT INTO users VALUES (?, ?)",
                           (username, password))
                db.execute("INSERT INTO commits (request) VALUES (?)",
                           (json.dumps(request),))
                db.commit()

                return {
                    "status": "OK",
                }
        elif request["action_type"] == "LOGIN":
            with sqlite3.connect(self.db_file) as db:
                # Check if the passwords match
                cursor = db.execute("SELECT password FROM users WHERE username = ?",
                                    (request["username"],))
                db_password, = cursor.fetchone()
                if password != db_password:
                    return self.create_error("Invalid username or password.")

                return {
                    "status": "OK",
                }
        else:
            raise ValueError("Invalid authentication action type.")

    def handle_get_messages(self, request: dict) -> dict:
        assert request["request_type"] == "GET_MESSAGES"

        # Get the username to fetch messages for
        username = request["username"]

        # Query the DB
        with sqlite3.connect(self.db_file) as db:
            cursor = db.execute("""
                SELECT sender, body, timestamp, read
                FROM messages
                WHERE recipient = ?
                ORDER BY timestamp
            """, (username,))
            rows = cursor.fetchall()

        # Parse the messages
        messages = [
            {
                "sender": sender,
                "body": body,
                "timestamp": timestamp,
                "read": bool(read),
            }
            for (sender, body, timestamp, read) in rows
        ]

        return {
            "status": "OK",
            "messages": messages,
        }

    def handle_list_users(self, request: dict) -> dict:
        assert request["request_type"] == "LIST_USERS"

        # Get the wildcard pattern
        pattern = request["pattern"]

        # Query the DB
        with sqlite3.connect(self.db_file) as db:
            cursor = db.execute("SELECT username FROM users WHERE username GLOB ?",
                                (pattern,))
            rows = cursor.fetchall()

        # Return the usernames
        usernames = [row[0] for row in rows]

        return {
            "status": "OK",
            "usernames": usernames,
        }

    def handle_send_message(self, request: dict) -> dict:
        assert request["request_type"] == "SEND_MESSAGE"

        # Grab the message contents
        message = request["message"]
        message_id = message["id"]
        sender = message["sender"]
        recipient = message["recipient"]
        body = message["body"]
        timestamp = message["timestamp"]

        with sqlite3.connect(self.db_file) as db:
            # First check whether the recipient exists
            cursor = db.execute("SELECT username FROM users WHERE username = ?",
                                (recipient,))
            if cursor.fetchone() is None:
                return self.create_error("Recipient does not exist.")

            # Insert the new message into the DB
            db.execute("INSERT INTO messages VALUES (?, ?, ?, ?, ?)",
                       (message_id, sender, recipient, body, timestamp))
            db.execute("INSERT INTO commits (request) VALUES (?)",
                       (json.dumps(request),))
            db.commit()

        return {
            "status": "OK",
        }

    def handle_read_messages(self, request: dict) -> dict:
        assert request["request_type"] == "READ_MESSAGES"

        # Grab the message IDs
        message_ids: list[str] = request["message_ids"]

        with sqlite3.connect(self.db_file) as db:
            # Create a list of '?' placeholders
            placeholders = ",".join(["?"] * len(message_ids))

            # Query the DB
            db.execute(f"UPDATE messages SET read = 1 WHERE id in ({placeholders})",
                       message_ids)
            db.execute("INSERT INTO commits (request) VALUES (?)",
                       (json.dumps(request),))
            db.commit()

        return {
            "status": "OK",
        }

    def handle_delete_messages(self, request: dict) -> dict:
        assert request["request_type"] == "DELETE_MESSAGES"

        # IDs of the messages to delete
        message_ids = request["message_ids"]

        with sqlite3.connect(self.db_file) as db:
            # Create a list of '?' placeholders
            placeholders = ",".join(["?"] * len(message_ids))

            # Query the DB
            db.execute(f"DELETE FROM messages WHERE id in ({placeholders})",
                       message_ids)
            db.execute("INSERT INTO commits (request) VALUES (?)",
                       (json.dumps(request),))
            db.commit()

        return {
            "status": "OK",
        }

    def handle_delete_user(self, request: dict) -> dict:
        assert request["request_type"] == "DELETE_USER"

        # Username of the user to delete
        username = request["username"]

        with sqlite3.connect(self.db_file) as db:
            db.execute("DELETE FROM users WHERE username = ?",
                       (username,))
            db.execute("INSERT INTO commits (request) VALUES (?)",
                       (json.dumps(request),))
            db.commit()

        return {
            "status": "OK",
        }

    @staticmethod
    def create_error(error_message: str) -> dict:
        return {
            "status": "ERROR",
            "error_message": error_message,
        }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", type=int, required=True, help="Unique ID for this server.")
    args = parser.parse_args()

    # Fixed known addresses for 3-server cluster.
    # Suppose all are on localhost with different ports. You can change to actual IP addresses.
    id_to_addr = get_id_to_addr_map()
    server_id = args.id

    # Create the server and bind to addr
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=1))

    # Bind the server
    addr = id_to_addr[server_id]
    print(f"[Server {server_id}] Binding to {addr}...")
    if server.add_insecure_port(id_to_addr[server_id]) == 0:
        raise ValueError(f"Failed to bind to port {id_to_addr[server_id]}")

    # Add chat server
    add_ChatServicer_to_server(ChatServer(server_id), server)

    # Start
    server.start()

    try:
        while True:
            time.sleep(5)  # Keep alive
    except KeyboardInterrupt:
        print(f"Server {server_id} shutting down...")
        server.stop(0)


if __name__ == "__main__":
    main()
