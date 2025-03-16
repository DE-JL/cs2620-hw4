from PyQt5.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton


class LoggedIn(QWidget):
    """
    Logged-in class for the user banner at the top of the screen.
    """

    def __init__(self):
        super().__init__()

        self.logged_in_layout = QHBoxLayout()
        self.user_label = QLabel("Logged in as: ")
        self.delete_account_button = QPushButton("Delete Account")
        self.sign_out_button = QPushButton("Sign Out")

        self.logged_in_layout.addWidget(self.user_label)
        self.logged_in_layout.addWidget(self.delete_account_button)
        self.logged_in_layout.addWidget(self.sign_out_button)

        self.setLayout(self.logged_in_layout)

    def update_user_label(self, username):
        self.user_label.setText(f"Logged in as: {username}")
