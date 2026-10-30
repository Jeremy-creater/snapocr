"""M9 WI-19: in-window shortcuts use ⌘ on a Mac, and the hints say so (PRD F23-5). Offscreen.

On a Mac Qt reports the Command key as ``ControlModifier`` and the Control key
as ``MetaModifier`` (measured in WI-8), so the key handling written for Ctrl
already answers ⌘. What changes is the text: ⌘Enter, ⌘Z, ⌘S.

Pinned here (beyond the plan text):
- ``shortcut_text(name, *, platform)`` for translate / undo / save; Windows
  text unchanged; an unknown name or platform is a ``ValueError``.
- The Control key (Qt's Meta) with Z, S or Enter does nothing on a Mac.
"""

import pytest
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QColor, QImage, QKeyEvent
from PySide6.QtWidgets import QApplication, QToolButton

from snapocr.geometry import Rect, ScreenInfo
from snapocr.gui.annotate_toolbar import AnnotateToolbar
from snapocr.gui.overlay import SelectionOverlay
from snapocr.gui.popup import TranslationPopup
from snapocr.hotkeys import shortcut_text
from support import qt_input as qi

pytestmark = pytest.mark.usefixtures("qapp")

M = Qt.KeyboardModifier
SCREEN = ScreenInfo("A", Rect(0, 0, 800, 600), 1.0, Rect(0, 0, 800, 600))


@pytest.mark.parametrize(
    ("name", "windows", "mac"),
    [("translate", "Ctrl+Enter", "⌘Enter"), ("undo", "Ctrl+Z", "⌘Z"), ("save", "Ctrl+S", "⌘S")],
)
def test_shortcut_text(name, windows, mac):
    assert shortcut_text(name) == shortcut_text(name, platform="win32") == windows
    assert shortcut_text(name, platform="darwin") == mac


@pytest.mark.parametrize("call", [lambda: shortcut_text("copy"), lambda: shortcut_text("undo", platform="linux")])
def test_unknown_names_and_platforms(call):
    with pytest.raises(ValueError):
        call()


def test_the_translation_window_hint_on_a_mac(qtbot):
    window = TranslationPopup(platform="darwin")
    qtbot.addWidget(window)
    assert window.hint_label.text() == "⌘Enter"
    assert window.translate_button.toolTip() == "翻译原文（⌘Enter）"


def test_the_toolbar_tips_on_a_mac(qtbot):
    bar = AnnotateToolbar(platform="darwin")
    qtbot.addWidget(bar)
    assert bar.findChild(QToolButton, "undo").toolTip() == "撤销（⌘Z）"
    assert bar.findChild(QToolButton, "save").toolTip() == "另存为图片，同时复制（⌘S）"


def _key(widget, key, mods):
    QApplication.sendEvent(widget, QKeyEvent(QEvent.Type.KeyPress, key, mods))


def _overlay_with_a_mark(qtbot):
    image = QImage(800, 600, QImage.Format.Format_RGB32)
    image.fill(QColor(200, 200, 200))
    overlay = SelectionOverlay(image, SCREEN, annotate=True, platform="darwin")
    qtbot.addWidget(overlay)
    qi.drag(overlay, 100, 100, 300, 250)
    overlay.toolbar.findChild(QToolButton, "tool-rect").click()
    qi.drag(overlay, 120, 120, 200, 200)
    assert len(overlay.marks) == 1
    return overlay


def test_the_overlay_toolbar_follows_the_platform(qtbot):
    overlay = _overlay_with_a_mark(qtbot)
    assert overlay.toolbar.findChild(QToolButton, "undo").toolTip() == "撤销（⌘Z）"


def test_control_z_does_not_undo_but_command_z_does(qtbot):
    overlay = _overlay_with_a_mark(qtbot)
    _key(overlay, Qt.Key.Key_Z, M.MetaModifier)  # the Control key on a Mac
    assert len(overlay.marks) == 1
    _key(overlay, Qt.Key.Key_Z, M.ControlModifier)  # the Command key
    assert overlay.marks == ()


def test_control_s_does_not_save(qtbot):
    overlay = _overlay_with_a_mark(qtbot)
    _key(overlay, Qt.Key.Key_S, M.MetaModifier)
    assert overlay.save_dialog is None


def test_control_enter_does_not_translate_but_command_enter_does(qtbot):
    window = TranslationPopup(platform="darwin")
    qtbot.addWidget(window)
    window.show()
    window.source_view.setPlainText("Hello")
    with qtbot.assertNotEmitted(window.translate_requested):
        qtbot.keyClick(window.source_view, Qt.Key.Key_Return, M.MetaModifier)
    with qtbot.waitSignal(window.translate_requested, timeout=1000) as got:
        qtbot.keyClick(window.source_view, Qt.Key.Key_Return, M.ControlModifier)
    assert got.args[0].startswith("Hello")
