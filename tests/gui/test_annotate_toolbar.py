"""M4 WI-3: annotation toolbar (PRD F14-1, F14-4, F14-6; plan D12).

Pinned here:
- Buttons are found by object name: ``tool-rect``, ``tool-ellipse``,
  ``tool-arrow``, ``tool-text``, ``color-0`` .. ``color-7`` (``PALETTE``
  order), ``level-0`` .. ``level-2``, ``undo``, ``pin``, ``cancel``,
  ``done``. Each has a Chinese tooltip. None of them takes keyboard focus
  (Enter and Esc belong to the overlay).
- Tool buttons: at most one checked; clicking the checked one unchecks it.
  ``tool_changed`` carries the new tool or ``None``; ``tool`` reads it.
- Colour and level: exactly one of each checked, starting from the given
  style; a click on another one emits ``style_changed(Style)``, a click on the
  checked one emits nothing.
- ``color_clicked(str)`` and ``level_clicked(int)`` (F14-10) fire on every
  click of a colour or level, the current one included.
- Undo starts disabled; ``set_undo_enabled`` switches it. Undo, pin, cancel
  and done emit their signals. The pin button is hidden unless ``show_pin``.
"""

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QToolButton, QWidget

from snapocr.annotate import DEFAULT_STYLE, PALETTE, Style, Tool
from snapocr.gui.annotate_toolbar import AnnotateToolbar

pytestmark = pytest.mark.usefixtures("qapp")

TOOLS = {"tool-rect": Tool.RECT, "tool-ellipse": Tool.ELLIPSE, "tool-arrow": Tool.ARROW, "tool-text": Tool.TEXT}
NAMES = [*TOOLS, *(f"color-{i}" for i in range(8)), "level-0", "level-1", "level-2", "undo", "pin", "cancel", "done"]


def btn(bar: AnnotateToolbar, name: str) -> QToolButton:
    found = bar.findChild(QToolButton, name)
    assert found is not None, f"no button {name}"
    return found


class Rec:
    def __init__(self, bar: AnnotateToolbar):
        self.events: list[tuple[str, object]] = []
        bar.tool_changed.connect(lambda t: self.events.append(("tool", t)))
        bar.style_changed.connect(lambda s: self.events.append(("style", s)))
        bar.undo_requested.connect(lambda: self.events.append(("undo", None)))
        bar.pin_requested.connect(lambda: self.events.append(("pin", None)))
        bar.cancel_requested.connect(lambda: self.events.append(("cancel", None)))
        bar.done_requested.connect(lambda: self.events.append(("done", None)))


def checked(bar: AnnotateToolbar, prefix: str) -> list[str]:
    return [n for n in NAMES if n.startswith(prefix) and btn(bar, n).isChecked()]


def test_every_button_exists_with_a_tooltip_and_no_focus():
    bar = AnnotateToolbar(show_pin=True)
    for name in NAMES:
        b = btn(bar, name)
        assert b.toolTip(), name
        assert any("一" <= ch <= "鿿" for ch in b.toolTip()), name
        assert b.focusPolicy() == Qt.FocusPolicy.NoFocus, name


def test_initial_state():
    bar = AnnotateToolbar(Style(PALETTE[3], 0))
    assert bar.tool is None
    assert bar.style == Style(PALETTE[3], 0)
    assert checked(bar, "tool-") == []
    assert checked(bar, "color-") == ["color-3"]
    assert checked(bar, "level-") == ["level-0"]
    assert not btn(bar, "undo").isEnabled()


def test_default_style():
    bar = AnnotateToolbar()
    assert bar.style == DEFAULT_STYLE
    assert checked(bar, "color-") == ["color-0"] and checked(bar, "level-") == ["level-1"]


def test_tools_are_exclusive_and_toggle_off():
    bar = AnnotateToolbar()
    rec = Rec(bar)
    btn(bar, "tool-rect").click()
    assert bar.tool is Tool.RECT and checked(bar, "tool-") == ["tool-rect"]
    btn(bar, "tool-arrow").click()
    assert bar.tool is Tool.ARROW and checked(bar, "tool-") == ["tool-arrow"]
    btn(bar, "tool-arrow").click()
    assert bar.tool is None and checked(bar, "tool-") == []
    assert rec.events == [("tool", Tool.RECT), ("tool", Tool.ARROW), ("tool", None)]


@pytest.mark.parametrize("name", list(TOOLS))
def test_each_tool_button(name):
    bar = AnnotateToolbar()
    rec = Rec(bar)
    btn(bar, name).click()
    assert rec.events == [("tool", TOOLS[name])]


def test_colour_and_level_changes():
    bar = AnnotateToolbar()
    rec = Rec(bar)
    btn(bar, "color-4").click()
    btn(bar, "level-2").click()
    btn(bar, "color-7").click()
    assert rec.events == [
        ("style", Style(PALETTE[4], 1)),
        ("style", Style(PALETTE[4], 2)),
        ("style", Style(PALETTE[7], 2)),
    ]
    assert bar.style == Style(PALETTE[7], 2)
    assert checked(bar, "color-") == ["color-7"] and checked(bar, "level-") == ["level-2"]


def test_clicking_the_current_colour_or_level_emits_nothing():
    bar = AnnotateToolbar()
    rec = Rec(bar)
    btn(bar, "color-0").click()
    btn(bar, "level-1").click()
    assert rec.events == []
    assert checked(bar, "color-") == ["color-0"] and checked(bar, "level-") == ["level-1"]


def test_style_does_not_change_the_tool():
    bar = AnnotateToolbar()
    btn(bar, "tool-ellipse").click()
    btn(bar, "color-2").click()
    assert bar.tool is Tool.ELLIPSE


def test_undo_enabled_only_when_told():
    bar = AnnotateToolbar()
    rec = Rec(bar)
    btn(bar, "undo").click()
    assert rec.events == []
    bar.set_undo_enabled(True)
    assert btn(bar, "undo").isEnabled()
    btn(bar, "undo").click()
    bar.set_undo_enabled(False)
    btn(bar, "undo").click()
    assert rec.events == [("undo", None)]


def test_pin_cancel_done():
    bar = AnnotateToolbar(show_pin=True)
    rec = Rec(bar)
    for name in ("pin", "cancel", "done"):
        btn(bar, name).click()
    assert rec.events == [("pin", None), ("cancel", None), ("done", None)]


def test_pin_hidden_by_default():
    assert btn(AnnotateToolbar(), "pin").isHidden()
    assert not btn(AnnotateToolbar(show_pin=True), "pin").isHidden()


def test_has_a_usable_size():
    bar = AnnotateToolbar()
    hint = bar.sizeHint()
    assert hint.width() > hint.height() > 0


def test_toolbar_paints_its_own_light_panel():
    """M4 bug fix: a QWidget subclass ignores its stylesheet background unless styled backgrounds are on."""
    parent = QWidget()  # stands in for the dimmed overlay
    pal = parent.palette()
    pal.setColor(QPalette.ColorRole.Window, Qt.GlobalColor.black)
    parent.setPalette(pal)
    parent.setAutoFillBackground(True)
    parent.resize(1000, 100)
    bar = AnnotateToolbar(parent=parent)
    bar.setGeometry(10, 10, bar.sizeHint().width(), bar.sizeHint().height())
    shot = parent.grab().toImage()
    c = shot.pixelColor(10 + bar.width() // 2, 12)  # between the border and the buttons
    assert min(c.red(), c.green(), c.blue()) >= 230, c.name()


def test_every_colour_and_level_click_is_reported():
    bar = AnnotateToolbar()
    clicks = []
    bar.color_clicked.connect(lambda c: clicks.append(("color", c)))
    bar.level_clicked.connect(lambda lv: clicks.append(("level", lv)))
    btn(bar, "color-0").click()  # the current one
    btn(bar, "color-4").click()
    btn(bar, "level-1").click()  # the current one
    btn(bar, "level-2").click()
    assert clicks == [("color", PALETTE[0]), ("color", PALETTE[4]), ("level", 1), ("level", 2)]
