import os
import pytest
import signal
import subprocess
import sys
import time
import uuid

# Add the root directory to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from api import *
from config import PUBLIC_STATUS


@pytest.fixture(scope="session", autouse=True)
def clean_databases():
    """Run `make clean` once before the test session starts."""
    print("\n🧹 Running `make clean` to clear the databases...")
    subprocess.run(["make", "clean"], check=True)
    print("✅ Done cleaning.")


class ServerManager:
    """Encapsulates starting/stopping servers for more direct usage in tests."""

    def __init__(self):
        self.procs: dict[int, subprocess.Popen] = {}

    def start(self, server_id: int):
        """Start a server with a given ID."""
        proc = subprocess.Popen(["python", "server.py", "--id", str(server_id)])
        self.procs[server_id] = proc
        time.sleep(1)

    def stop(self, server_id: int):
        """Stop a specific server."""
        proc = self.procs.get(server_id)

        # Send keyboard interrupt
        proc.send_signal(signal.SIGINT)
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()

    def start_all(self):
        """Start all servers."""
        for server_id in [1, 2, 3]:
            self.start(server_id)

    def stop_all(self):
        """Stop all servers."""
        for server_id in self.procs:
            self.stop(server_id)


@pytest.fixture
def server_manager():
    """Pytest fixture that starts all servers and allows control during test."""
    assert PUBLIC_STATUS == False, "Tests must be run with PUBLIC_STATUS=False"

    # Create server manager and start all the servers
    manager = ServerManager()
    manager.start_all()

    # Yield the manager to the test case
    yield manager

    # Stop the servers
    manager.stop_all()


def test_auth(server_manager):
    # Login to a user that doesn't exist
    exp = {
        "status": "ERROR",
        "error_message": "Invalid username or password.",
    }
    resp = login("jason", "password")
    assert resp == exp

    # Create a user
    exp = {
        "status": "OK",
    }
    resp = create_user("jason", "password")
    assert resp == exp

    # Create the same user (should fail)
    exp = {
        "status": "ERROR",
        "error_message": "Username already exists.",
    }
    resp = create_user("jason", "password")
    assert resp == exp

    # Successfully login
    exp = {
        "status": "OK",
    }
    resp = login("jason", "password")
    assert resp == exp

    # Wrong password
    exp = {
        "status": "ERROR",
        "error_message": "Invalid username or password.",
    }
    resp = login("jason", "wrong_password")
    assert resp == exp


def test_get_and_send(server_manager):
    # Test sending to a nonexistent recipient
    message_0 = {
        "id": str(uuid.uuid4()),
        "sender": "jason",
        "recipient": "daniel",
        "body": "Hello, world!",
        "timestamp": 0,
    }
    assert send_message(message_0) == {
        "status": "ERROR",
        "error_message": "Recipient does not exist.",
    }

    # Send some messages
    message_1 = {
        "id": str(uuid.uuid4()),
        "sender": "daniel",
        "recipient": "jason",
        "body": "Hello world!",
        "timestamp": 1.0,
    }
    message_2 = {
        "id": str(uuid.uuid4()),
        "sender": "daniel",
        "recipient": "jason",
        "body": "Goodbye world!",
        "timestamp": 2.0,
    }
    assert send_message(message_1) == {"status": "OK"}
    assert send_message(message_2) == {"status": "OK"}

    # Fetch the messages (they should be sorted by LATEST first!)
    assert get_messages("jason") == {
        "status": "OK",
        "messages": [
            {
                **message_2,
                "read": False,
            },
            {
                **message_1,
                "read": False,
            },
        ],
    }


def test_list_users(server_manager):
    # Match
    assert list_users("j*") == {
        "status": "OK",
        "usernames": ["jason"],
    }

    # No matches
    assert list_users("z*") == {
        "status": "OK",
        "usernames": [],
    }


def test_read_messages(server_manager):
    # Get all messages for "jason"
    resp = get_messages("jason")
    msgs = resp["messages"]

    # Get the message IDs and send a read request
    msg_ids = [msg["id"] for msg in msgs]
    assert read_messages(msg_ids) == {"status": "OK"}

    # Fetch messages again and assert that their status has changed
    resp = get_messages("jason")
    msgs = resp["messages"]
    for msg in msgs:
        assert msg["read"] == True


def test_delete_messages(server_manager):
    # Get all messages for "jason"
    resp = get_messages("jason")
    msgs = resp["messages"]

    # Delete the messages
    msg_ids = [msg["id"] for msg in msgs]
    assert delete_messages(msg_ids) == {"status": "OK"}

    # They should not exist anymore
    resp = get_messages("jason")
    msgs = resp["messages"]
    assert msgs == []


def test_delete_user(server_manager):
    # Send a message
    message = {
        "id": str(uuid.uuid4()),
        "sender": "jason",
        "recipient": "jason",
        "body": "foobar",
        "timestamp": 0,
    }
    assert send_message(message) == {"status": "OK"}

    # Delete jason
    resp = delete_user("jason")
    assert resp == {"status": "OK"}

    # Fetch all the users -- there should be no users
    assert list_users("*") == {
        "status": "OK",
        "usernames": [],
    }

    # Fetch messages for "jason", there should be none
    assert get_messages("jason") == {
        "status": "OK",
        "messages": [],
    }


def test_fault_tolerant_auth(server_manager):
    # Create two new users
    assert create_user("rajiv", "password") == {"status": "OK"}
    assert create_user("daniel", "password") == {"status": "OK"}

    # Stop servers 3 and 1
    server_manager.stop(3)
    server_manager.stop(1)

    # Log new users in
    assert login("rajiv", "password") == {"status": "OK"}
    assert login("daniel", "password") == {"status": "OK"}

    # Start server 1 and stop 2
    server_manager.start(1)
    server_manager.stop(2)

    # Testing list users
    assert list_users("dan*") == {
        "status": "OK",
        "usernames": ["daniel"],
    }
    assert list_users("raj*") == {
        "status": "OK",
        "usernames": ["rajiv"],
    }
    assert list_users("z*") == {
        "status": "OK",
        "usernames": [],
    }


def test_fault_tolerant_messaging(server_manager):
    # Start 2 and stop 1
    server_manager.start(2)
    server_manager.stop(1)

    # Send a message
    message = {
        "id": str(uuid.uuid4()),
        "sender": "daniel",
        "recipient": "rajiv",
        "body": "how is it going?",
        "timestamp": 5.0,
    }
    exp = {"status": "OK"}
    resp = send_message(message)
    assert resp == exp

    # Start server 3
    server_manager.start(3)

    # Fetch message
    resp = get_messages("rajiv")
    exp = {
        "status": "OK",
        "messages": [
            {
                **message,
                "read": False,
            }
        ]
    }
    assert resp == exp


def test_fault_tolerant_deletes(server_manager):
    # Stop 1 and 3
    server_manager.stop(1)
    server_manager.stop(3)

    # Delete user "rajiv"
    assert delete_user("rajiv") == {"status": "OK"}

    # Should only be "daniel" left
    assert list_users("*") == {
        "status": "OK",
        "usernames": ["daniel"],
    }

    # Should not be any more messages for "rajiv"
    assert get_messages("rajiv") == {
        "status": "OK",
        "messages": [],
    }

    # Send a message to "daniel"
    message_0 = {
        "id": str(uuid.uuid4()),
        "sender": "daniel",
        "recipient": "daniel",
        "body": "am i talking to me?",
        "timestamp": 3.9,
    }
    assert send_message(message_0) == {"status": "OK"}

    # Get all messages for "daniel"
    resp = get_messages("daniel")
    messages = resp["messages"]
    message_ids = [message["id"] for message in messages]

    # Start 3 and kill 2
    server_manager.start(3)
    server_manager.stop(2)

    # Delete all messages for "daniel"
    assert delete_messages(message_ids) == {"status": "OK"}

    # Start 1 and kill 3
    server_manager.start(1)
    server_manager.stop(3)

    # Should be no more messages
    assert get_messages("daniel") == {
        "status": "OK",
        "messages": [],
    }
