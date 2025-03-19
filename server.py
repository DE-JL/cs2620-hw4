import argparse
import sqlite3
import threading
import time

from concurrent import futures

from protos.chat_pb2 import *
from protos.chat_pb2_grpc import *
from utils import get_ip_to_addr_map


class ChatServer(ChatServicer):
    """Server implementation for the bully election algorithm."""

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
        self.id_to_addr = get_ip_to_addr_map()

        # Initialize the database
        self.db_file = f"server{self.server_id}.db"
        self.init_db()

        # Initially, we don’t know the leader yet
        self.leader_id = None

        # For concurrency control
        self.lock = threading.Lock()

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
            new_commits = [commit for commit in request.commit_history if commit.id > latest_commit_id]
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
                    query TEXT NOT NULL
                )
            """)

            # Create the messages table
            db.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id BLOB PRIMARY KEY,
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
            cursor = db.execute("SELECT id, query FROM commits ORDER BY id")
            rows = cursor.fetchall()

        return [Commit(id=row[0], query=row[1]) for row in rows]

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
        with sqlite3.connect(self.db_file) as db:
            for commit in commits:
                db.execute("INSERT INTO commits VALUES (?, ?)",
                           (commit.id, commit.query))
                db.execute(commit.query)
            db.commit()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", type=int, required=True, help="Unique ID for this server.")
    args = parser.parse_args()

    # Fixed known addresses for 3-server cluster.
    # Suppose all are on localhost with different ports. You can change to actual IP addresses.
    id_to_addr = get_ip_to_addr_map()
    server_id = args.id

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=1))
    add_ChatServicer_to_server(ChatServer(server_id), server)
    server.add_insecure_port(id_to_addr[server_id])
    server.start()

    try:
        while True:
            time.sleep(5)  # Keep alive
    except KeyboardInterrupt:
        print(f"Server {server_id} shutting down...")
        server.stop(0)


if __name__ == "__main__":
    main()
