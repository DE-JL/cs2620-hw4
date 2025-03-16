from datetime import datetime

from PyQt5.QtWidgets import QLabel, QListWidget, QWidget, QListWidgetItem
from PyQt5.QtWidgets import QVBoxLayout, QHBoxLayout, QAbstractItemView
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QIntValidator, QValidator
from PyQt5.QtWidgets import QPushButton
from PyQt5.QtWidgets import QLineEdit



class ViewMessage(QWidget):
    """
    View message class for viewing the delivered count and reading/deleting messages.
    """

    def __init__(self):
        super().__init__()

        self.frame_layout = QHBoxLayout()
        self.frame_layout.setSpacing(0)
        self.frame_layout.setContentsMargins(0, 0, 0, 0)

        self.frame_label = QLabel("View Messages")

        # TODO add validation to input here
        self.unread_count_label = QLabel("Unread Messages")
        self.num_read_label = QLabel("Number of Messages to Read: ")
        self.num_read_entry = QLineEdit("1")
        self.num_read_entry.setValidator(NoLeadingZeroValidator(1, 100))
        self.read_button = QPushButton("Read Messages")

        self.unread_box = QVBoxLayout()
        self.unread_box.addWidget(self.frame_label)
        self.unread_box.addWidget(self.unread_count_label)
        self.unread_box.addWidget(self.num_read_label)
        self.unread_box.addWidget(self.num_read_entry)
        self.unread_box.addWidget(self.read_button)

        self.delete_button = QPushButton("Delete Selected")
        self.unread_box.addWidget(self.delete_button)

        self.message_list = QListWidget()
        self.message_list.setSelectionMode(QAbstractItemView.MultiSelection)
        self.message_list.setFont(QFont("Courier", 10))

        self.frame_layout.addLayout(self.unread_box)
        self.frame_layout.addWidget(self.message_list)

        self.setLayout(self.frame_layout)

    def update_message_list(self, messages: list):
        # Get the set if message IDs of selected messages
        selected_ids = set()
        for item in self.message_list.selectedItems():
            msg = item.data(Qt.UserRole)
            selected_ids.add(msg.id)

        # Block UI updates
        self.message_list.blockSignals(True)
        self.message_list.clear()

        # Rerender each message one by one
        num_unread = 0
        for message in messages:
            if not message.read:
                num_unread += 1
                continue

            # Convert timestamp to a readable string
            time_str = datetime.fromtimestamp(message.timestamp).strftime('%Y-%m-%d %H:%M:%S')

            # Create a display string
            display_text = f"[{time_str}] {message.sender}: {message.body}"

            # Create a list item
            item = QListWidgetItem(display_text)

            # Store the entire Message object in user data and add it to the list
            item.setData(Qt.UserRole, message)
            self.message_list.addItem(item)

            # Make sure previously selected items are selected
            if message.id in selected_ids:
                item.setSelected(True)

        # Unblock UI updates
        self.message_list.blockSignals(False)
        self.message_list.repaint()
        self.unread_count_label.setText(f"Unread: {num_unread}")


class NoLeadingZeroValidator(QIntValidator):
    """
    Input validator utility class.
    """

    def validate(self, input_str: str, pos: int):
        # Allow empty input (to support deletion)
        if input_str == "":
            return QValidator.Intermediate, input_str, pos

        # Prevent leading zeros unless the number is just "0"
        if input_str.startswith("0") and len(input_str) > 1:
            return QValidator.Invalid, input_str, pos

        # Check if input is a valid integer
        try:
            num = int(input_str)
        except ValueError:
            return QValidator.Invalid, input_str, pos

        # Ensure it's within the valid range
        if self.bottom() <= num <= self.top():
            return QValidator.Acceptable, input_str, pos
        else:
            return QValidator.Invalid, input_str, pos
