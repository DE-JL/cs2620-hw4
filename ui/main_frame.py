from .logged_in import LoggedIn
from .login import Login
from .central import Central
from .view_message import ViewMessage

from PyQt5.QtWidgets import QFrame, QVBoxLayout


class MainFrame(QFrame):
    """
    Main frame class for the application.
    """

    def __init__(self):
        super().__init__()

        self.login = Login()
        self.logged_in = LoggedIn()
        self.central = Central()
        self.view_messages = ViewMessage()

        # Set up the frame layout
        main_frame_layout = QVBoxLayout()
        main_frame_layout.setSpacing(0)
        main_frame_layout.setContentsMargins(0, 0, 0, 0)

        # Add application frames
        main_frame_layout.addWidget(self.login)
        main_frame_layout.addWidget(self.logged_in)
        main_frame_layout.addWidget(self.central)
        main_frame_layout.addWidget(self.view_messages)

        self.setLayout(main_frame_layout)
