from PyQt5.QtWidgets import QWidget, QGridLayout, QLabel, QLineEdit, QTextEdit, QPushButton


class SendMessage(QWidget):
    """
    Send message class.
    """

    def __init__(self):
        super().__init__()

        self.frame_layout = QGridLayout()
        self.frame_layout.setSpacing(0)
        self.frame_layout.setContentsMargins(0, 0, 0, 0)

        self.frame_label = QLabel("Send Message")

        self.recipient_label = QLabel("Recipient: ")
        self.recipient_entry = QLineEdit()

        self.message_label = QLabel("Message: ")
        self.message_text = QTextEdit()

        self.send_button = QPushButton("Send")

        self.frame_layout.addWidget(self.frame_label, 0, 0, 1, 2)
        self.frame_layout.addWidget(self.recipient_label, 1, 0)
        self.frame_layout.addWidget(self.recipient_entry, 1, 1)
        self.frame_layout.addWidget(self.message_label, 2, 0)
        self.frame_layout.addWidget(self.message_text, 2, 1)
        self.frame_layout.addWidget(self.send_button, 3, 0, 1, 2)

        self.setLayout(self.frame_layout)
