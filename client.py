import uuid

from api import *


def test_auth():
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
    resp = login("jason", "wrongpassword")
    assert resp == exp


def test_get_and_send():
    # Test sending to a nonexistent recipient
    msg0 = {
        "id": str(uuid.uuid4()),
        "sender": "jason",
        "recipient": "daniel",
        "body": "Hello, world!",
        "timestamp": 0,
    }
    exp = {
        "status": "ERROR",
        "error_message": "Recipient does not exist.",
    }
    resp = send_message(msg0)
    assert resp == exp

    # Send some messages
    msg1 = {
        "id": str(uuid.uuid4()),
        "sender": "daniel",
        "recipient": "jason",
        "body": "Hello world!",
        "timestamp": 1.0,
        "read": False,
    }
    msg2 = {
        "id": str(uuid.uuid4()),
        "sender": "daniel",
        "recipient": "jason",
        "body": "Goodbye world!",
        "timestamp": 2.0,
        "read": False,
    }
    assert send_message(msg1) == {"status": "OK"}
    assert send_message(msg2) == {"status": "OK"}

    # Fetch the messages
    exp = {
        "status": "OK",
        "messages": [msg1, msg2],
    }
    resp = get_messages("jason")
    assert resp == exp


def test_list_users():
    # Match
    exp = {
        "status": "OK",
        "usernames": ["jason"],
    }
    resp = list_users("j*")
    assert resp == exp

    # No matches
    exp = {
        "status": "OK",
        "usernames": [],
    }
    resp = list_users("z*")
    assert resp == exp


def test_read_messages():
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


def test_delete_messages():
    # Get all messages for "jason"
    resp = get_messages("jason")
    msgs = resp["messages"]

    # Delete the messages
    msg_ids = [msg["id"] for msg in msgs]
    assert delete_messages(msg_ids) == {"status": "OK"}

    resp = get_messages("jason")
    msgs = resp["messages"]
    assert msgs == []


def test_delete_user():
    # Delete jason
    resp = delete_user("jason")
    assert resp == {"status": "OK"}

    # Fetch all the users
    exp = {
        "status": "OK",
        "usernames": [],
    }
    resp = list_users("*")
    assert resp == exp


def main():
    test_auth()
    test_get_and_send()
    test_list_users()
    test_read_messages()
    test_delete_messages()
    test_delete_user()


if __name__ == "__main__":
    main()
