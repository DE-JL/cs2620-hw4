import argparse
import hashlib
import threading
import uuid
import time

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QFrame, QListWidget, QWidget
from PyQt5.QtWidgets import QMainWindow, QDesktopWidget
from PyQt5.QtWidgets import QMessageBox, QLineEdit, QTextEdit
from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot
from PyQt5.QtCore import QThread
from sys import argv

import api

from config import GUI_REFRESH_RATE
from ui import MainFrame


class UserSession:
    """
    Represents a user's session for interacting with the server and managing
    user interactions in the application's main GUI.
    """

    def __init__(self, mainframe: MainFrame, window: QMainWindow):
        """
        Initialize a UserSession instance.

        :param mainframe: The main application frame.
        :param window: The main application window.
        """
        # GUI
        self.mainframe = mainframe
        self.window = window

        # Username of the logged-in user
        self.username = None

        # Message fetching
        self.message_thread = None
        self.message_worker = None
        self.messages = None

        # Register event handlers
        self.mainframe.login.login_button.clicked.connect(self.login_user)
        self.mainframe.login.sign_up_button.clicked.connect(self.sign_up)
        self.mainframe.logged_in.sign_out_button.clicked.connect(self.sign_out)
        self.mainframe.logged_in.delete_account_button.clicked.connect(self.delete_account)
        self.mainframe.central.list_account.search_button.clicked.connect(self.list_account_event)
        self.mainframe.central.send_message.send_button.clicked.connect(self.send_message_event)
        self.mainframe.view_messages.read_button.clicked.connect(self.read_messages_event)
        self.mainframe.view_messages.delete_button.clicked.connect(self.delete_messages_event)

    def close(self):
        """
        Close the connection to the server.

        If the client is not running in debug mode, this method will close the
        socket connection to the server. This method should be called when the
        client is finished interacting with the server.
        """
        pass

    def authenticate_user(self, request_type: str):
        """
        Authenticate the user with the given action type.

        :param request_type: The request type to use for authentication.
        """
        print("Authenticating user...")
        username = self.mainframe.login.user_entry.text()
        password = self.mainframe.login.password_entry.text()

        # Check if alphanumeric
        if not username.isalnum():
            QMessageBox.critical(self.window, 'Error', "Username must be alphanumeric")
            return

        # Hash the password
        password = hash_string(password)

        # Switch on the request type
        if request_type == "CREATE_USER":
            response = api.create_user(username, password)
        elif request_type == "LOGIN":
            response = api.login(username, password)
        else:
            raise ValueError(f"Invalid request type: {request_type}")

        # Check for authentication errors
        if response["status"] == "ERROR":
            QMessageBox.critical(self.window, 'Error', response["error_message"])
            return

        print("Authentication successful")

        # Hide the login frame
        self.mainframe.login.hide()

        # Show logged in frame
        self.mainframe.logged_in.show()
        self.mainframe.central.show()
        self.mainframe.view_messages.show()
        self.mainframe.logged_in.update_user_label(username)
        self.username = username

        self.start_logged_session()

    def sign_up(self):
        self.authenticate_user("CREATE_USER")

    def login_user(self):
        self.authenticate_user("LOGIN")

    def sign_out(self):
        """
        Sign the user out and go back to the login screen.
        If the client is not in debug mode, stop the session.
        :return: None
        """
        self.stop_logged_session()
        print("Signing out...")

        # Hide logged in frame
        self.mainframe.logged_in.hide()
        self.mainframe.central.hide()
        self.mainframe.view_messages.hide()

        # Show login frame
        self.mainframe.login.user_entry.setText("")
        self.mainframe.login.password_entry.setText("")
        self.mainframe.login.show()
        self.username = None

        clear_all_fields(self.mainframe)

    def delete_account(self):
        """
        Delete the currently logged-in user's account.

        This method sends a delete user request to the server and if the
        response is an error, it displays an error box with the response
        message. If the response is not an error, it successfully deletes the
        user's account and signs the user out.
        """
        # Save the username
        user_to_delete = self.username

        # Sign out
        self.sign_out()

        # Send the delete user request
        response = api.delete_user(user_to_delete)

        # Check for errors
        if response["status"] == "ERROR":
            QMessageBox.critical(self.window, 'Error', response["error_message"])
            return

        print("Account deleted")

    def list_account_event(self):
        """
        Handle the list account button event.

        This method is called when the search button in the list account frame is clicked.
        It sends a list users request to the server with the search string from the
        search entry and the currently logged-in user's username. If the response is an
        error, it displays an error box with the response message. If the response is not
        an error, it clears the list widget and populates it with the usernames returned
        in the response.
        """
        # Grab the glob pattern
        pattern = self.mainframe.central.list_account.search_entry.text()

        # Send the request
        response = api.list_users(pattern)

        # Check for errors
        if response["status"] == "ERROR":
            QMessageBox.critical(self.window, "Error", response["error_message"])
            return

        # Clear the usernames and display the new ones
        self.mainframe.central.list_account.account_list.clear()
        for idx, user in enumerate(response["usernames"]):
            self.mainframe.central.list_account.account_list.insertItem(idx, user)

    def send_message_event(self):
        """
        Handle the send message button event.

        This method is called when the send button in the send message frame is clicked.
        It constructs a message object from the sender, recipient, and body from the
        send message frame. It then sends a send message request to the server with the
        message object and the currently logged-in user's username. If the response is an
        error, it displays an error box with the response message. If the response is not
        an error, it clears all the fields in the send message frame.
        """
        # Parse the recipient and the message body
        recipient = self.mainframe.central.send_message.recipient_entry.text()
        message_body = self.mainframe.central.send_message.message_text.toPlainText()

        # Create the message object and send it to the server
        message = {
            "id": str(uuid.uuid4()),
            "sender": self.username,
            "recipient": recipient,
            "body": message_body,
            "timestamp": time.time(),
        }
        response = api.send_message(message)

        # Check for errors
        if response["status"] == "ERROR":
            QMessageBox.critical(self.window, "Error", response["error_message"])
            return

        # Clear the input fields
        clear_all_fields(self.mainframe.central.send_message)

    def handle_new_messages(self, messages):
        """
        Handle a new list of messages from the server.

        This method is called when a GetMessagesResponse is received from the server.
        It stores the messages in the messages attribute, sorts them by timestamp in
        descending order, and updates the messages list in the view messages frame.

        :param messages: The list of messages retrieved from the server.
        """
        self.messages = messages
        self.mainframe.view_messages.update_message_list(self.messages)

    def delete_messages_event(self):
        """
        Handle the delete message button event.

        This method is called when the delete button in the view messages frame is clicked.
        It constructs a delete message request object with the IDs of the selected messages
        and the currently logged-in user's username. It then sends the request to the server.
        If the response is an error, it displays an error box with the response message.
        If the response is not an error, it clears the messages list in the view messages frame.
        """
        # Grab the selected items
        selected_items = self.mainframe.view_messages.message_list.selectedItems()
        if not selected_items:
            print("No messages selected")
            return

        # Get the IDs of the selected messages (strings)
        message_ids = []
        for item in selected_items:
            # Retrieve the original Message object
            message = item.data(Qt.UserRole)
            message_ids.append(message["id"])

        # Send the request
        response = api.delete_messages(message_ids)

        # Check for errors
        if response["status"] == "ERROR":
            QMessageBox.critical(self.window, "Error", response["error_message"])
            return

    def read_messages_event(self):
        """
        Handle the read messages button event.

        This method is called when the read messages button in the view messages frame is clicked.
        It constructs a read message request object with the IDs of the selected messages
        and the currently logged-in user's username. It then sends the request to the server.
        If the response is an error, it displays an error box with the response message.
        If the response is not an error, it updates the messages list in the view messages frame
        to mark the messages as read.
        """
        # Get the number of messages to read
        try:
            num_to_read = int(self.mainframe.view_messages.num_read_entry.text())
        except ValueError:
            QMessageBox.critical(self.window, "Error", "Please enter a number of messages to read.")
            return

        # Get the message IDs and take a minimum
        message_ids = [message["id"] for message in self.messages if not message["read"]]
        num_to_read = min(num_to_read, len(message_ids))
        print("Number of messages to read:", num_to_read)

        # Edge case
        if num_to_read == 0:
            QMessageBox.critical(self.window, 'Error', "No messages to read")
            return

        # Get the earliest `num_to_read` message IDs
        message_ids = message_ids[-num_to_read:]

        # Send a read messages request
        response = api.read_messages(message_ids)

        # Check for errors
        if response["status"] == "ERROR":
            QMessageBox.critical(self.window, "Error", response["error_message"])
            return

    def start_logged_session(self):
        """
        Start the logged-in session.

        This method is called after a user logs in. It creates a MessageUpdaterWorker
        object with the server's hostname, port, the currently logged-in user's username,
        and an update interval of 0.1 seconds. It then creates a QThread object and moves
        the worker to the thread. It connects the worker's messages_received signal to
        the handle_new_messages method and starts the thread. This causes the worker to
        periodically poll the server for new messages and update the messages list in
        the view messages frame with the new messages.
        """
        self.message_worker = MessageUpdaterWorker(username=self.username)

        # Create the thread object
        self.message_thread = QThread()

        # Move the worker to the thread
        self.message_worker.moveToThread(self.message_thread)

        # When the thread starts, run the worker's main loop
        self.message_thread.started.connect(self.message_worker.run)

        # Connect the worker's signal to your handler in the main thread
        self.message_worker.messages_received.connect(self.handle_new_messages)

        # Start the thread
        self.message_thread.start()

    def stop_logged_session(self):
        """
        Stop the logged-in session.

        This method stops the MessageUpdaterWorker and the QThread that it is running in.
        It sends a stop signal to the worker, asks the thread to quit, waits for the thread to
        fully exit, and then cleans up the references to the worker and thread.
        """
        if self.message_worker and self.message_thread:
            # Signal the worker to stop
            self.message_worker.stop()

            # Ask the thread to quit (once run() returns)
            self.message_thread.quit()

            # Wait for the thread to fully exit
            self.message_thread.wait()

            # Cleanup references
            self.message_worker = None
            self.message_thread = None


class MessageUpdaterWorker(QObject):
    """
    Worker class to periodically fetch new messages for the logged-in user.
    """
    messages_received = pyqtSignal(list)

    def __init__(self, username: str, parent=None):
        """
        A class responsible for initializing a network fetcher session to communicate
        with the server, set up user details, and manage thread execution state.

        :param username: The username of the user to be used for authentication.
        :param parent: The GUI parent object.
        """
        super().__init__(parent)

        # Username of the logged-in user
        self.username = username

        # Status of fetcher thread
        self.running = threading.Event()

    @pyqtSlot()
    def run(self):
        """
        Start a separate thread to periodically poll the server for new messages
        and emit them via the messages_received signal.

        :return: None
        """
        self.running.set()

        # 2) Start polling loop
        while self.running.is_set():
            try:
                response = api.get_messages(self.username)
                if response["status"] == "ERROR":
                    print(f"[MessageUpdaterWorker] Error: {response["error_message"]}")
                else:
                    self.messages_received.emit(response["messages"])
            except Exception as e:
                print(f"[MessageUpdaterWorker] Error: {e}")
                # On any critical error, you might want to break or handle differently
                break

            # Sleep for the update interval (in seconds)
            time.sleep(GUI_REFRESH_RATE)

        # Shutdown
        print("[MessageUpdaterWorker] Worker thread stopped.")

    def stop(self):
        """
        Signal the worker loop to stop running.
        """
        self.running.clear()


def clear_all_fields(widget: QWidget | QFrame):
    """
    Recursively clear all form fields and list widgets in a given widget tree.

    Walks the widget tree of the given widget, clearing all QLineEdit, QTextEdit, and QListWidget
    instances, as well as any QFrame or QWidget instances that may contain nested widgets.

    :param widget: The root of the widget tree to clear.
    :type widget: QWidget | QFrame
    """
    for child in widget.findChildren(QWidget):
        if isinstance(child, (QLineEdit, QTextEdit, QListWidget)):
            child.clear()
        elif isinstance(child, (QFrame, QWidget)):  # Recursively clear nested containers
            clear_all_fields(child)


def create_window(mainframe: MainFrame) -> QMainWindow:
    """
    Create a window with a specified main frame, and set its title and initial size.

    :param mainframe: The widget to set as the central widget of the window.
    :type mainframe: QWidget
    :return: The created window, ready to be shown.
    :rtype: QMainWindow
    """
    window = QMainWindow()
    window.setWindowTitle("Message App: Design Exercise")
    window.setCentralWidget(mainframe)
    screen_size = QDesktopWidget().screenGeometry()
    window.resize(int(3 * screen_size.width() / 4), screen_size.height() // 2)
    return window


def hash_string(input_string):
    """
    Hash the given input string using SHA-256.

    :param input_string: The string to hash.
    :type input_string: str
    :return: The hashed string, as a hexadecimal string.
    :rtype: str
    """
    return hashlib.sha256(input_string.encode()).hexdigest()


def post_app_exit_tasks(user_session):
    """
    Perform tasks that should be done when the application exits.

    :param user_session: The user session to close.
    :type user_session: UserSession
    """
    print("Closing user session...")
    user_session.close()


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False, description="GUI for the Message App Design Exercise")
    args = parser.parse_args()

    # Load GUI
    app = QApplication(argv)

    # Create mainframe and window
    mainframe = MainFrame()
    window = create_window(mainframe)
    mainframe.logged_in.hide()
    mainframe.central.hide()
    mainframe.view_messages.hide()

    # Start the user session
    user_session = UserSession(mainframe, window)

    # display GUI
    window.show()

    app.aboutToQuit.connect(lambda: post_app_exit_tasks(user_session))
    exit(app.exec())


if __name__ == "__main__":
    main()
