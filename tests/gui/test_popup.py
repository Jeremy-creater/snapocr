"""M2 WI-15: translation popup (PRD F8-1 to F8-4).

Pinned here:
- ``apply(job_id, state)`` returns whether the event was taken:
  - a job id newer than the current one (or the first) is taken in any
    state, and shows the popup;
  - for the current job only ``Translating -> Done | Failed`` is taken;
  - everything else (older ids, a second terminal state, Translating again)
    is ignored and changes nothing.
- Translating: the translation area reads ``TRANSLATING_TEXT``; "copy
  translation" is disabled, "copy source" enabled. Done: both enabled.
  Failed: the translation area shows the message; only "copy source".
- The translation area is read-only (the source is editable since PRD v1.3,
  see test_translation_window.py). Copy buttons write the exact text.
- Esc hides the popup. A later state for the same job updates the content
  but does not show it again; a new job does.
- ``place(anchor, available)``: geometry == ``place_popup(anchor, size,
  available)`` and lies inside ``available`` (logical coordinates).
"""

import threading

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QGuiApplication

from snapocr.actions.flows import FlowDeps
from snapocr.actions.history import ResultHistory
from snapocr.actions.outcomes import Done, Failed, Translating
from snapocr.actions.runner import JobRunner, TranslateDone, TranslateStarted, translate_job
from snapocr.engines.types import OcrResult
from snapocr.geometry import Rect, place_popup
from snapocr.gui.bridge import EventBridge
from snapocr.gui.popup import TRANSLATING_TEXT, TranslationPopup
from snapocr.postprocess import PostprocessOptions, Replacements
from snapocr.translators.types import TranslationResult
from support import qt_input as qi
from support.fake_actions import holder_for
from support.pp_strategies import rect

SENTINEL = "snapocr-sentinel-clipboard"
SRC = "今天天气很好"
TR = "The weather is nice today"


@pytest.fixture
def clipboard(qapp):
    cb = QGuiApplication.clipboard()
    cb.setText(SENTINEL)
    yield cb
    cb.clear()


@pytest.fixture
def popup(qtbot):
    widget = TranslationPopup()
    qtbot.addWidget(widget)
    return widget


def shown(popup):
    return {
        "source": popup.source_view.toPlainText(),
        "translation": popup.translation_view.toPlainText(),
        "copy_source": popup.copy_source_button.isEnabled(),
        "copy_translation": popup.copy_translation_button.isEnabled(),
    }


# --- states and buttons (F8-2, F8-3, F8-4) -----------------------------------------


def test_initial_popup_is_hidden_and_empty(popup):
    assert popup.job_id is None and popup.state is None
    assert not popup.isVisible()


def test_translating(popup):
    assert popup.apply(1, Translating(SRC)) is True
    assert popup.isVisible()
    assert shown(popup) == {"source": SRC, "translation": TRANSLATING_TEXT, "copy_source": True, "copy_translation": False}
    # PRD v1.3 F19-2: the source box is editable now; the translation box stays read-only.
    assert not popup.source_view.isReadOnly() and popup.translation_view.isReadOnly()


def test_done_copies_both_texts(popup, clipboard, qtbot):
    popup.apply(1, Translating(SRC))
    assert popup.apply(1, Done(SRC, TR)) is True
    assert shown(popup) == {"source": SRC, "translation": TR, "copy_source": True, "copy_translation": True}
    qtbot.mouseClick(popup.copy_translation_button, Qt.MouseButton.LeftButton)
    assert clipboard.text() == TR
    qtbot.mouseClick(popup.copy_source_button, Qt.MouseButton.LeftButton)
    assert clipboard.text() == SRC


def test_failed_shows_message_and_keeps_clipboard(popup, clipboard, qtbot):
    popup.apply(1, Translating(SRC))
    assert popup.apply(1, Failed(SRC, "翻译失败：连接不上")) is True
    assert shown(popup) == {"source": SRC, "translation": "翻译失败：连接不上", "copy_source": True, "copy_translation": False}
    qtbot.mouseClick(popup.copy_translation_button, Qt.MouseButton.LeftButton)  # disabled: no effect
    assert clipboard.text() == SENTINEL
    qtbot.mouseClick(popup.copy_source_button, Qt.MouseButton.LeftButton)
    assert clipboard.text() == SRC


def test_multiline_texts_are_shown_exactly(popup):
    popup.apply(3, Done("第一行\n第二行", "line one\nline two"))
    assert shown(popup)["source"] == "第一行\n第二行"
    assert shown(popup)["translation"] == "line one\nline two"


# --- transitions -----------------------------------------------------------------------


def test_terminal_state_is_final_for_its_job(popup):
    popup.apply(1, Translating(SRC))
    popup.apply(1, Done(SRC, TR))
    assert popup.apply(1, Failed(SRC, "late")) is False
    assert popup.apply(1, Translating(SRC)) is False
    assert popup.apply(1, Done(SRC, "other")) is False
    assert popup.state == Done(SRC, TR)
    assert shown(popup)["translation"] == TR


def test_translating_twice_for_one_job_is_ignored(popup):
    popup.apply(1, Translating(SRC))
    assert popup.apply(1, Translating("other")) is False
    assert shown(popup)["source"] == SRC


def test_older_job_events_are_ignored(popup):
    popup.apply(2, Translating("new"))
    assert popup.apply(1, Done("old", "old tr")) is False
    assert popup.apply(1, Translating("old")) is False
    assert popup.job_id == 2 and popup.state == Translating("new")
    assert shown(popup)["source"] == "new"


def test_new_job_reuses_the_popup_and_replaces_content(popup):
    popup.apply(1, Translating(SRC))
    popup.apply(1, Done(SRC, TR))
    assert popup.apply(2, Translating("second")) is True
    assert popup.job_id == 2
    assert shown(popup) == {"source": "second", "translation": TRANSLATING_TEXT, "copy_source": True, "copy_translation": False}


def test_newer_job_may_start_with_a_terminal_state(popup):
    popup.apply(1, Translating(SRC))
    assert popup.apply(5, Failed("x", "msg")) is True
    assert popup.job_id == 5 and popup.state == Failed("x", "msg")


# --- Esc and visibility (F8-1) -----------------------------------------------------------


def test_esc_hides_and_late_result_does_not_reshow(popup):
    popup.apply(1, Translating(SRC))
    qi.key(popup, Qt.Key.Key_Escape)
    assert not popup.isVisible()
    assert popup.apply(1, Done(SRC, TR)) is True
    assert not popup.isVisible()
    assert shown(popup)["translation"] == TR
    popup.apply(2, Translating("again"))
    assert popup.isVisible()


@pytest.mark.parametrize(
    "anchor",
    [Rect(100, 100, 200, 50), Rect(100, 1000, 200, 50), Rect(1800, 500, 100, 100), Rect(0, 0, 1920, 1080)],
    ids=["below", "above", "side", "covers-all"],
)
def test_place_uses_place_popup_inside_available(popup, anchor):
    available = Rect(0, 0, 1920, 1040)
    popup.place(anchor, available)
    expected = place_popup(anchor, (popup.width(), popup.height()), available)
    assert popup.geometry() == QRect(expected.x, expected.y, expected.w, expected.h)
    g = popup.geometry()
    assert available.x <= g.x() and available.y <= g.y()
    assert g.x() + g.width() <= available.x + available.w and g.y() + g.height() <= available.y + available.h


def test_place_on_a_small_screen_shrinks_to_fit(popup):
    available = Rect(-1707, 0, 300, 200)
    popup.place(Rect(-1600, 50, 50, 50), available)
    g = popup.geometry()
    assert g.width() <= 300 and g.height() <= 200
    assert -1707 <= g.x() and g.x() + g.width() <= -1407


# --- F8-2: the GUI stays responsive while translation blocks --------------------------------


class BlockingTranslator:
    def __init__(self):
        self.release = threading.Event()

    def translate(self, text, target=None):
        self.release.wait(30)
        return TranslationResult(f"T({text})", "en", False)


def test_popup_stays_responsive_while_translation_blocks(qtbot, popup):
    bridge = EventBridge()

    def on_event(event):
        if isinstance(event, TranslateStarted):
            popup.apply(event.job_id, Translating(event.stage.text))
        elif isinstance(event, TranslateDone):
            popup.apply(event.job_id, event.outcome.popup)

    bridge.event.connect(on_event)
    translator = BlockingTranslator()
    deps = FlowDeps(holder_for(OcrResult((rect("你好", 0, 0, 40, 20),))), PostprocessOptions(), Replacements.from_mapping({}))
    runner = JobRunner(bridge.post, ResultHistory())
    try:
        runner.submit(translate_job(b"png", deps, translator))
        qtbot.waitUntil(lambda: popup.state == Translating("你好"), timeout=5000)
        qtbot.wait(50)  # the event loop keeps running while the worker blocks
        assert popup.isVisible()
        qi.key(popup, Qt.Key.Key_Escape)
        assert not popup.isVisible()
        translator.release.set()
        qtbot.waitUntil(lambda: popup.state == Done("你好", "T(你好)"), timeout=5000)
    finally:
        translator.release.set()
        runner.shutdown()


# --- property: only legal transitions; older ids change nothing ------------------------------

STATES = st.one_of(
    st.builds(Translating, st.sampled_from(["a", "b"])),
    st.builds(Done, st.sampled_from(["a", "b"]), st.sampled_from(["x", "y"])),
    st.builds(Failed, st.sampled_from(["a", "b"]), st.sampled_from(["m", "n"])),
)


@settings(max_examples=40, deadline=None)
@given(st.lists(st.tuples(st.integers(1, 5), STATES), max_size=20))
def test_only_legal_transitions(qapp, events):
    popup = TranslationPopup()
    try:
        history = []  # (job_id, state) actually taken
        for job_id, state in events:
            before = (popup.job_id, popup.state)
            taken = popup.apply(job_id, state)
            after = (popup.job_id, popup.state)
            if not taken:
                assert after == before
                continue
            assert after == (job_id, state)
            if history:
                last_id, last_state = history[-1]
                assert job_id > last_id or (
                    job_id == last_id and isinstance(last_state, Translating) and not isinstance(state, Translating)
                )
            history.append((job_id, state))
        ids = [j for j, _ in history]
        assert ids == sorted(ids)
        for job_id in set(ids):
            kinds = [type(s) for j, s in history if j == job_id]
            assert len(kinds) <= 2
            if len(kinds) == 2:
                assert kinds[0] is Translating and kinds[1] is not Translating
    finally:
        popup.deleteLater()


# --- added after the first green (coverage) ------------------------------------------


def test_other_keys_do_not_hide(popup):
    popup.apply(1, Translating(SRC))
    qi.key(popup, Qt.Key.Key_A)
    qi.key(popup, Qt.Key.Key_Return)
    assert popup.isVisible()


def test_copy_keeps_exact_line_breaks(popup, clipboard, qtbot):
    popup.apply(1, Done("a\r\nb\u2029c", "x\r\ny"))
    qtbot.mouseClick(popup.copy_source_button, Qt.MouseButton.LeftButton)
    assert clipboard.text() == "a\r\nb\u2029c"
    qtbot.mouseClick(popup.copy_translation_button, Qt.MouseButton.LeftButton)
    assert clipboard.text() == "x\r\ny"
