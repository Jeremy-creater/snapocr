"""A segmented control: one checked button out of a few (PRD F20-5; M7 plan D9).

Offers the ``QComboBox`` calls the translation window and its controller use
(``addItem``, ``count``, ``itemText``, ``itemData``, ``currentIndex``,
``setCurrentIndex``, ``currentData``, ``currentIndexChanged``), so it replaces
the old target-language combo box without other changes. Styled by the
window's stylesheet through the object name ``segment``.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QButtonGroup, QHBoxLayout, QPushButton, QWidget


class SegmentedControl(QWidget):
    currentIndexChanged = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent, objectName="segment")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)  # the stylesheet paints the track
        self._data: list[object] = []
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._group.idToggled.connect(self._toggled)
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(2, 2, 2, 2)
        self._layout.setSpacing(0)

    @property
    def segment_buttons(self) -> tuple[QPushButton, ...]:
        return tuple(self._group.button(i) for i in range(len(self._data)))

    def addItem(self, text: str, data: object = None) -> None:
        button = QPushButton(text)
        button.setCheckable(True)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._group.addButton(button, len(self._data))
        self._data.append(data)
        self._layout.addWidget(button)
        if len(self._data) == 1:
            button.setChecked(True)

    def count(self) -> int:
        return len(self._data)

    def itemText(self, index: int) -> str:
        return self._group.button(index).text()

    def itemData(self, index: int) -> object:
        return self._data[index]

    def currentIndex(self) -> int:
        return self._group.checkedId()

    def currentData(self) -> object:
        return self._data[self.currentIndex()]

    def setCurrentIndex(self, index: int) -> None:
        self._group.button(index).setChecked(True)

    def _toggled(self, index: int, checked: bool) -> None:
        if checked:
            self.currentIndexChanged.emit(index)
