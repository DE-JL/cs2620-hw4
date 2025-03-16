import argparse
import hashlib
import uuid
import time

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QFrame, QListWidget, QWidget
from PyQt5.QtWidgets import QMainWindow, QDesktopWidget
from PyQt5.QtWidgets import QMessageBox, QLineEdit, QTextEdit
from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot
from PyQt5.QtCore import QThread
from sys import argv

from config import GUI_REFRESH_RATE
from protos.chat_pb2 import *
from protos.chat_pb2_grpc import *
from ui import MainFrame


class UserSession:
    """
    A class to represent a socket-based user session
    """

    def __init__(self, host: str, port: int, mainframe: MainFrame, window: QMainWindow):
        """
        Initialize a UserSession instance.

        :param host: The hostname or IP address of the server
        :param port: The port number to connect to the server on
        :param mainframe: The main application frame
        :param window: The main application window
        """
        self.mainframe = mainframe
        self.window = window
        self.username = None

        self.host = host
        self.port = port
        self.channel = None
        self.stub = None

        self.message_thread = None
        self.message_worker = None
        self.messages = None

        # Initialize connection for main GUI thread
        try:
            server_addr = f"{self.host}:{self.port}"
            self.channel = grpc.insecure_channel(server_addr)
            self.stub = ChatStub(self.channel)
        except Exception as e:
            print("Connection refused. Please check if the server is running.")
            print(e)
            exit(1)

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
        self.channel.close()
        self.channel = None
        self.stub = None

    def authenticate_user(self, action):
        """
        Authenticate the user with the given action type.

        This method will attempt to authenticate the user with the given action type
        (either AuthRequest.ActionType.LOGIN or AuthRequest.ActionType.CREATE_ACCOUNT).
        If the authentication is successful, the client will enter the logged in state.

        If the client is running in debug mode and the username is "admin" and the
        password is "pass", the client will automatically be authenticated and enter
        the logged in state.

        If the authentication fails, the client will display an error message to the user.

        :param action: The action type to use for authentication.
        :type action: api.AuthRequest.ActionType
        """
        print("Authenticating user...")
        username = self.mainframe.login.user_entry.text()
        password = self.mainframe.login.password_entry.text()

        # Check if alphanumeric
        if not username.isalnum():
            QMessageBox.critical(self.window, 'Error', "Username must be alphanumeric")
            return

        # Hash the password
        hashed_password = hash_string(password)

        response = self.stub.Authenticate(AuthRequest(action_type=action, username=username, password=hashed_password))

        if response.status == Status.ERROR:
            QMessageBox.critical(self.window, 'Error', response.error_message)
            return

        print("Authentication successful")

        # hide the login frame
        self.mainframe.login.hide()
        # show logged in frame
        self.mainframe.logged_in.show()
        self.mainframe.central.show()
        self.mainframe.view_messages.show()
        self.mainframe.logged_in.update_user_label(username)
        self.username = username

        self.start_logged_session()

    def sign_up(self):
        self.authenticate_user(AuthRequest.ActionType.CREATE_ACCOUNT)

    def login_user(self):
        self.authenticate_user(AuthRequest.ActionType.LOGIN)

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

        :return: None
        """
        user_to_delete = self.username

        self.sign_out()

        response = self.stub.DeleteUser(DeleteUserRequest(username=user_to_delete))

        if response.status == Status.ERROR:
            QMessageBox.critical(self.window, 'Error', response.error_message)
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

        :return: None
        """
        search_string = self.mainframe.central.list_account.search_entry.text()

        response = self.stub.ListUsers(ListUsersRequest(username=self.username, pattern=search_string))

        if response.status == Status.ERROR:
            QMessageBox.critical(self.window, 'Error', response.error_message)
            return

        self.mainframe.central.list_account.account_list.clear()
        for idx, user in enumerate(response.usernames):
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

        :return: None
        """
        recipient = self.mainframe.central.send_message.recipient_entry.text()
        message_body = self.mainframe.central.send_message.message_text.toPlainText()

        message = Message(id=uuid.uuid4().bytes,
                          sender=self.username,
                          recipient=recipient,
                          body=message_body,
                          timestamp=time.time())
        req = SendMessageRequest(username=self.username, message=message)

        response = self.stub.SendMessage(req)

        if response.status == Status.ERROR:
            QMessageBox.critical(self.window, 'Error', response.error_message)
            return

        clear_all_fields(self.mainframe.central.send_message)

    def handle_new_messages(self, messages):
        """
        Handle a new list of messages from the server.

        This method is called when a GetMessagesResponse is received from the server.
        It stores the messages in the messages attribute, sorts them by timestamp in
        descending order, and updates the messages list in the view messages frame.

        :param messages: The list of messages retrieved from the server.
        :type messages: list[Message]
        :return: None
        """
        self.messages = messages
        self.messages.sort(key=lambda x: x.timestamp, reverse=True)
        self.mainframe.view_messages.update_message_list(self.messages)

    def delete_messages_event(self):
        """
        Handle the delete message button event.

        This method is called when the delete button in the view messages frame is clicked.
        It constructs a delete message request object with the IDs of the selected messages
        and the currently logged-in user's username. It then sends the request to the server.
        If the response is an error, it displays an error box with the response message.
        If the response is not an error, it clears the messages list in the view messages frame.

        :return: None
        """
        selected_items = self.mainframe.view_messages.message_list.selectedItems()
        if not selected_items:
            print("No messages selected")
            return  # Nothing to delete

        ids_to_delete = []
        for item in selected_items:
            # Retrieve the original Message object
            msg = item.data(Qt.UserRole)
            ids_to_delete.append(msg.id)

        response = self.stub.DeleteMessages(DeleteMessagesRequest(username=self.username, message_ids=ids_to_delete))

        if response.status == Status.ERROR:
            QMessageBox.critical(self.window, 'Error', response.error_message)
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

        :return: None
        """
        try:
            num_to_read = int(self.mainframe.view_messages.num_read_entry.text())
        except ValueError:
            QMessageBox.critical(self.window, 'Error', "Please enter a valid number of messages to read")
            return

        ids = [message.id for message in self.messages if not message.read]

        num_to_read = min(num_to_read, len(ids))

        print("Number of messages to read:", num_to_read)

        if num_to_read == 0:
            QMessageBox.critical(self.window, 'Error', "No messages to read")
            return

        ids = ids[-num_to_read:]

        # make read message request
        response = self.stub.ReadMessages(ReadMessagesRequest(username=self.username, message_ids=ids))

        if response.status == Status.ERROR:
            QMessageBox.critical(self.window, 'Error', response.error_message)
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

        :return: None
        """
        self.message_worker = MessageUpdaterWorker(host=self.host,
                                                   port=self.port,
                                                   username=self.username)

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
    Worker class to periodically fetch new messages from a separate socket connection.
    """
    messages_received = pyqtSignal(list)  # emitted when new messages arrive

    def __init__(self, host: str, port: int, username: str, parent=None):
        """
        :param host: Server's hostname or IP address
        :param port: Server's port
        :param username: The current user's name (for message queries, if needed)
        """
        super().__init__(parent)

        self.host = host
        self.port = port
        self.username = username

        self.running = False
        self.channel = None
        self.stub = None

    @pyqtSlot()
    def run(self):
        """
        Start a separate thread to periodically poll the server for new messages
        and emit them via the messages_received signal.

        :return: None
        """
        self.running = True

        self.channel = grpc.insecure_channel(f"{self.host}:{self.port}")
        self.stub = ChatStub(self.channel)

        # 2) Start polling loop
        while self.running:
            try:
                response = self.stub.GetMessages(GetMessagesRequest(username=self.username))

                if response.status == Status.ERROR:
                    print(f"[MessageUpdaterWorker] Error: {response.error_message}")
                else:
                    self.messages_received.emit(list(response.messages))

            except Exception as e:
                print(f"[MessageUpdaterWorker] Error: {e}")
                # On any critical error, you might want to break or handle differently
                break

            # Sleep for the update interval (in seconds)
            time.sleep(GUI_REFRESH_RATE)

        # Cleanup
        if self.channel:
            self.channel.close()
            self.stub = None
        print("[MessageUpdaterWorker] Worker thread stopped.")

    def stop(self):
        """
        Signal the worker loop to stop running.
        """
        self.running = False


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
    parser.add_argument("host", type=str, metavar='host', help="The host on which the server is running")
    parser.add_argument("port", type=int, metavar='port', help="The port at which the server is listening")
    args = parser.parse_args()

    # load GUI
    app = QApplication(argv)

    mainframe = MainFrame()
    window = create_window(mainframe)

    print("Trying to connect to server...")
    mainframe.logged_in.hide()
    mainframe.central.hide()
    mainframe.view_messages.hide()
    user_session = UserSession(args.host, args.port, mainframe, window)

    # display GUI
    window.show()

    app.aboutToQuit.connect(lambda: post_app_exit_tasks(user_session))
    exit(app.exec())


if __name__ == "__main__":
    main()
