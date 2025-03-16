from PyQt5.QtWidgets import QWidget, QLabel, QLineEdit, QPushButton, QGridLayout
from PyQt5.QtCore import Qt


class Login(QWidget):
    """
    Login class for the user signup/login window.
    """

    def __init__(self):
        super().__init__()

        self.user_label = QLabel("User: ")
        self.user_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.user_label.setAutoFillBackground(True)

        self.password_label = QLabel("Password: ")
        self.password_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.password_label.setAutoFillBackground(True)

        self.user_entry = QLineEdit()
        self.password_entry = QLineEdit()
        self.password_entry.setEchoMode(QLineEdit.Password)

        self.login_button = QPushButton("Login")

        self.sign_up_button = QPushButton("Sign Up")

        self.entry_layout = QGridLayout()
        self.entry_layout.addWidget(self.user_label, 0, 0)
        self.entry_layout.addWidget(self.user_entry, 0, 1)
        self.entry_layout.addWidget(self.password_label, 1, 0)
        self.entry_layout.addWidget(self.password_entry, 1, 1)
        self.entry_layout.addWidget(self.login_button, 2, 0)
        self.entry_layout.addWidget(self.sign_up_button, 2, 1)

        self.setLayout(self.entry_layout)
