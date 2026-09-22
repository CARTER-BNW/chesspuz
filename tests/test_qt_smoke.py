"""Proves the offscreen Qt test setup works on this machine."""

from PySide6.QtWidgets import QLabel


def test_qtbot_shows_a_widget(qtbot) -> None:
    label = QLabel("chesspuz")
    qtbot.addWidget(label)
    label.show()
    assert label.text() == "chesspuz"
