from PyQt5.QtWidgets import QWidget, QLabel, QLineEdit, QPushButton
from PyQt5.QtWidgets import QAbstractItemView, QListWidget
from PyQt5.QtWidgets import QHBoxLayout, QVBoxLayout
from PyQt5.QtWidgets import QFrame


class ListUsers(QWidget):
    """
    List users class for user search section.
    """

    def __init__(self):
        super().__init__()

        self.frame_layout = QVBoxLayout()
        self.frame_layout.setSpacing(0)
        self.frame_layout.setContentsMargins(0, 0, 0, 0)

        self.frame_label = QLabel("Search Users")
        self.entry_label = QLabel("Search: ")
        self.search_entry = QLineEdit()
        self.search_button = QPushButton("Search")
        self.account_list = QListWidget()
        self.account_list.setSelectionMode(QAbstractItemView.MultiSelection)

        self.frame_layout.addWidget(self.frame_label)

        self.entry_box = QHBoxLayout()
        self.entry_box.addWidget(self.entry_label)
        self.entry_box.addWidget(self.search_entry)
        self.entry_box.addWidget(self.search_button)

        self.frame_layout.addLayout(self.entry_box)
        self.frame_layout.addWidget(self.account_list)

        self.frame = QFrame()
        self.setLayout(self.frame_layout)
