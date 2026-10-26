"""M2 WI-17: application controller (PRD F5-1, F5-3, F5-5, F6-3, F7-1 to F7-5, F8, F9-3, F10-1).

Real Qt widgets (offscreen), real JobRunner and EventBridge, real clipboard
(in-process). Fakes: capture provider, notifier, hotkey table, open_file,
quit_app, OCR engine, translator.

Pinned here:
- ``start()`` registers the hotkeys, shows a config-issues notice (if any)
  then a hotkey-failure notice (if any), and submits the engine warm-up.
- ``handle_hotkey(id)`` runs the command registered under that id; unknown
  or unregistered ids are ignored. ``run(command)`` runs it directly. Menu
  actions run capture commands on the next event-loop turn (after the menu
  has closed); the other commands at once.
- Capture commands take one capture and open an overlay session over every
  screen (``overlays``); while a session is open, further capture commands
  are ignored. ``CaptureError`` -> "截图失败" notice, no session.
- Cancelled selection: no clipboard change, no notice (F6-3).
- CAPTURE: the PNG of the selection on the clipboard + "已复制截图" (F7-1).
- OCR / TRANSLATE are jobs; OcrDone -> clipboard + notice (F7-2 to F7-4);
  TranslateStarted -> popup Translating, placed next to the selection inside
  the screen's work area (logical; the screen's logical rect if none given);
  TranslateDone -> popup state and clipboard (F7-5, F8). Each finished job
  refreshes an open last-results window.
- JobCrashed -> "操作失败" notice; a popup waiting on that job shows Failed.
- LAST_RESULT opens the last-results window on the newest entry (F10-1).
- OPEN_CONFIG: a missing file is first created from the template (never
  overwriting); then ``open_file(path)`` and "修改后重启 snapocr 生效".
  Creation failure -> config-issues notice and nothing opened; ``open_file``
  raising OSError -> "无法打开配置文件".
- QUIT: hotkeys released, runner shut down, session / popup / window
  closed, ``quit_app()`` called; a second QUIT does nothing more.
"""

import threading
from pathlib import Path

import pytest
from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QGuiApplication

from snapocr.actions.flows import FlowDeps
from snapocr.actions.messages import preview
from snapocr.actions.outcomes import Done, Failed, Translating
from snapocr.commands import Command
from snapocr.config.schema import AppConfig, ConfigIssue
from snapocr.config.template import DEFAULT_TEMPLATE
from snapocr.engines.errors import EngineLoadError
from snapocr.engines.holder import EngineHolder
from snapocr.engines.types import OcrResult
from snapocr.geometry import Rect, ScreenInfo, logical_rect, place_popup
from snapocr.gui.controller import AppController
from snapocr.gui.imageops import crop, decode_png
from snapocr.hotkeys import hotkey_id, parse_hotkey
from snapocr.postprocess import PostprocessOptions, Replacements, postprocess
from snapocr.translators.types import TranslationResult
from support import qt_input as qi
from support.fake_actions import ScriptedEngine, ScriptedTranslator, holder_for
from support.fake_desktop import FakeCapture, RecordingNotifier, desktop_image
from support.fake_hotkeys import FakeHotkeyTable
from support.pp_strategies import rect
from support.qimages import pixels

SENTINEL = "snapocr-sentinel-clipboard"
MAIN = ScreenInfo("MAIN", Rect(0, 0, 800, 600), 1.0, Rect(0, 0, 800, 600))
SIDE = ScreenInfo("SIDE", Rect(800, 0, 400, 300), 1.5, Rect(800, 0, 600, 450))
WORK = {"MAIN": Rect(0, 0, 800, 560)}
TABLE = Replacements.from_mapping({"0CR": "OCR"})
RESULT = OcrResult((rect("使用0CR截图识别，", 0, 0, 200, 20), rect("Hello World", 0, 40, 120, 60)))
EXPECTED = postprocess(RESULT, PostprocessOptions(), TABLE)
WAIT = 5000


@pytest.fixture
def clipboard(qapp):
    cb = QGuiApplication.clipboard()
    cb.setText(SENTINEL)
    yield cb
    cb.clear()


class Harness:
    def __init__(self, qtbot, tmp_path, *, engine=RESULT, load_error=None, holder=None, translator=None,
                 capture_error=None, issues=(), preoccupy=(), config_path=None):
        self.capture = FakeCapture(desktop_image(1400, 600), (0, 0), (MAIN, SIDE), dict(WORK), capture_error)
        self.notifier = RecordingNotifier()
        self.table = FakeHotkeyTable()
        for text in preoccupy:
            hk = parse_hotkey(text)
            self.table.preoccupy(hk.mods, hk.vk)
        self.opened: list[Path] = []
        self.open_error: OSError | None = None
        self.quits: list[bool] = []
        self.config_path = config_path or tmp_path / "config.local.toml"
        config = AppConfig(replacements=TABLE)
        deps = FlowDeps(holder or holder_for(engine, load_error=load_error), config.postprocess, config.replacements)
        self.controller = AppController(
            config,
            self.config_path,
            deps,
            translator or ScriptedTranslator(),
            capture_provider=self.capture,
            notifier=self.notifier,
            hotkey_backend=self.table,
            open_file=self._open,
            quit_app=lambda: self.quits.append(True),
            startup_issues=list(issues),
        )
        self.qtbot = qtbot

    def _open(self, path):
        if self.open_error is not None:
            raise self.open_error
        self.opened.append(path)

    def titles(self):
        return [n.title for n in self.notifier.notices]

    def select(self, x0=10, y0=10, x1=110, y1=70, screen=0, confirm=True):
        overlay = self.controller.overlays[screen]
        qi.drag(overlay, x0, y0, x1, y1)
        if confirm:
            qi.key(overlay, Qt.Key.Key_Return)

    def menu_action(self, command):
        labels = {Command.CAPTURE: "截图", Command.OCR: "OCR", Command.TRANSLATE: "翻译", Command.LAST_RESULT: "上次结果",
                  Command.OPEN_CONFIG: "打开配置文件", Command.QUIT: "退出"}
        return next(a for a in self.controller.menu.actions() if a.text().split("\t")[0] == labels[command])


@pytest.fixture
def make(qtbot, tmp_path, clipboard):
    made = []

    def factory(**kw):
        h = Harness(qtbot, tmp_path, **kw)
        made.append(h)
        h.controller.start()
        return h

    yield factory
    for h in made:
        h.controller.run(Command.QUIT)


# --- start-up (F5-3, F9-3) ---------------------------------------------------------------


def test_start_registers_all_default_hotkeys(make):
    h = make()
    assert sorted(h.table.ours) == sorted(hotkey_id(c) for c in (Command.CAPTURE, Command.OCR, Command.TRANSLATE, Command.LAST_RESULT))
    assert h.notifier.notices == []


def test_failed_hotkey_is_reported_and_others_work(make):
    h = make(preoccupy=["Alt+2"])
    (notice,) = h.notifier.notices
    assert "Alt+2" in notice.body and "OCR" in notice.body
    h.controller.handle_hotkey(hotkey_id(Command.OCR))  # not ours: ignored
    assert h.controller.overlays == ()
    h.controller.handle_hotkey(hotkey_id(Command.CAPTURE))
    assert len(h.controller.overlays) == 2


def test_unknown_hotkey_id_is_ignored(make):
    h = make()
    h.controller.handle_hotkey(999)
    assert h.controller.overlays == ()


def test_config_issues_are_reported_first(make, tmp_path):
    issue = ConfigIssue(tmp_path / "config.local.toml", "translator.timeout_s", "must be > 0")
    h = make(issues=[issue], preoccupy=["Alt+1"])
    assert h.titles() == ["配置文件有 1 个问题", "有 1 个热键注册失败"]
    body = h.notifier.notices[0].body
    assert "config.local.toml" in body and "translator.timeout_s" in body and "must be > 0" in body


def test_start_warms_up_the_engine(make):
    loads = []
    holder = EngineHolder(lambda: (loads.append(1), ScriptedEngine(RESULT))[1])
    h = make(holder=holder)
    h.qtbot.waitUntil(lambda: loads == [1], timeout=WAIT)


# --- capture sessions (F6, F7-1) ----------------------------------------------------------


def test_capture_opens_one_overlay_per_screen_with_its_part(make):
    h = make()
    h.controller.run(Command.CAPTURE)
    main, side = h.controller.overlays
    assert main.isVisible() and side.isVisible()
    assert main.geometry() == QRect(0, 0, 800, 600) and side.geometry() == QRect(800, 0, 400, 300)
    assert len(h.capture.taken) == 1


def test_capture_puts_selection_png_on_clipboard(make, clipboard):
    h = make()
    h.controller.run(Command.CAPTURE)
    h.select(10, 20, 110, 70)
    mime = clipboard.mimeData()
    assert mime.hasImage()
    got = decode_png(bytes(mime.data("image/png")))
    assert pixels(got) == pixels(crop(h.capture.image, Rect(10, 20, 100, 50)))
    assert h.titles() == ["已复制截图"]
    assert h.controller.overlays == ()


def test_capture_on_scaled_side_screen_uses_physical_pixels(make, clipboard):
    h = make()
    h.controller.run(Command.CAPTURE)
    h.select(10, 10, 110, 60, screen=1)  # logical 100x50 at 150% -> physical 150x75
    got = decode_png(bytes(clipboard.mimeData().data("image/png")))
    assert pixels(got) == pixels(crop(h.capture.image, Rect(815, 15, 150, 75)))


def test_cancelled_selection_changes_nothing(make, clipboard):
    h = make()
    h.controller.run(Command.OCR)
    qi.key(h.controller.overlays[1], Qt.Key.Key_Escape)
    assert clipboard.text() == SENTINEL
    assert h.notifier.notices == []
    assert h.controller.overlays == ()
    h.controller.run(Command.CAPTURE)  # a new session can start
    assert len(h.controller.overlays) == 2


def test_capture_commands_are_ignored_while_a_session_is_open(make):
    h = make()
    h.controller.run(Command.OCR)
    first = h.controller.overlays
    h.controller.handle_hotkey(hotkey_id(Command.TRANSLATE))
    h.controller.run(Command.CAPTURE)
    assert h.controller.overlays == first
    assert len(h.capture.taken) == 1


def test_capture_error_is_reported(make, clipboard):
    h = make(capture_error="BitBlt failed")
    h.controller.run(Command.CAPTURE)
    assert h.controller.overlays == ()
    assert h.titles() == ["截图失败"]
    assert "BitBlt failed" in h.notifier.notices[0].body
    assert clipboard.text() == SENTINEL


# --- OCR (F7-2 to F7-4) --------------------------------------------------------------------


def test_ocr_puts_postprocessed_text_on_clipboard(make, clipboard):
    h = make()
    h.controller.run(Command.OCR)
    h.select()
    h.qtbot.waitUntil(lambda: clipboard.text() == EXPECTED, timeout=WAIT)
    assert "OCR" in EXPECTED and "0CR" not in EXPECTED
    h.qtbot.waitUntil(lambda: h.titles() == ["已复制 OCR 文本"], timeout=WAIT)
    assert h.notifier.notices[0].body == preview(EXPECTED)


@pytest.mark.parametrize("kind", ["empty", "load-fail", "crash"])
def test_ocr_failures_keep_the_clipboard(make, clipboard, kind):
    if kind == "empty":
        h = make(engine=OcrResult(()))
        title = "未识别到文字"
    elif kind == "load-fail":
        h = make(load_error=EngineLoadError(model_paths=("m.onnx",), hint="reinstall", detail="missing"))
        title = "OCR 引擎加载失败"
    else:
        h = make(engine=RuntimeError("boom"))
        title = "操作失败"
    h.controller.run(Command.OCR)
    h.select()
    h.qtbot.waitUntil(lambda: title in h.titles(), timeout=WAIT)
    assert clipboard.text() == SENTINEL


def test_menu_and_hotkey_give_the_same_result(make, clipboard):
    h = make()
    h.controller.handle_hotkey(hotkey_id(Command.OCR))
    h.select()
    h.qtbot.waitUntil(lambda: clipboard.text() == EXPECTED, timeout=WAIT)
    via_hotkey = (clipboard.text(), len(h.controller.history.snapshot()))
    clipboard.setText(SENTINEL)
    h.menu_action(Command.OCR).trigger()
    assert h.controller.overlays == ()  # deferred until the menu has closed
    h.qtbot.waitUntil(lambda: len(h.controller.overlays) == 2, timeout=WAIT)
    h.select()
    h.qtbot.waitUntil(lambda: clipboard.text() == EXPECTED, timeout=WAIT)
    assert (clipboard.text(), len(h.controller.history.snapshot()) - 1) == via_hotkey


# --- TRANSLATE (F7-5, F8) ---------------------------------------------------------------------


class GatedTranslator:
    def __init__(self):
        self.gate = threading.Event()

    def translate(self, text):
        self.gate.wait(30)
        return TranslationResult(f"T({text})", "en", False)


def test_translate_goes_through_translating_to_done(make, clipboard):
    translator = GatedTranslator()
    h = make(translator=translator)
    popup = h.controller.popup
    try:
        h.controller.run(Command.TRANSLATE)
        h.select(100, 100, 300, 160)
        h.qtbot.waitUntil(lambda: popup.state == Translating(EXPECTED), timeout=WAIT)
        assert popup.isVisible()
        assert clipboard.text() == SENTINEL
        anchor = logical_rect(MAIN, Rect(100, 100, 200, 60))
        expected = place_popup(anchor, (popup.width(), popup.height()), WORK["MAIN"])
        assert popup.geometry() == QRect(expected.x, expected.y, expected.w, expected.h)
    finally:
        translator.gate.set()
    h.qtbot.waitUntil(lambda: popup.state == Done(EXPECTED, f"T({EXPECTED})"), timeout=WAIT)
    assert clipboard.text() == f"T({EXPECTED})"


def test_popup_on_screen_without_work_area_uses_its_logical_rect(make):
    h = make()
    h.controller.run(Command.TRANSLATE)
    h.select(10, 10, 110, 60, screen=1)
    popup = h.controller.popup
    h.qtbot.waitUntil(lambda: isinstance(popup.state, Done), timeout=WAIT)
    g = popup.geometry()
    assert 800 <= g.x() and g.x() + g.width() <= 1200 and 0 <= g.y() and g.y() + g.height() <= 300


def test_translate_with_empty_ocr_ends_like_ocr(make, clipboard):
    h = make(engine=OcrResult(()))
    h.controller.run(Command.TRANSLATE)
    h.select()
    h.qtbot.waitUntil(lambda: "未识别到文字" in h.titles(), timeout=WAIT)
    assert not h.controller.popup.isVisible()
    assert clipboard.text() == SENTINEL


def test_translator_crash_fails_the_popup(make, clipboard):
    h = make(translator=ScriptedTranslator(ZeroDivisionError()))
    h.controller.run(Command.TRANSLATE)
    h.select()
    popup = h.controller.popup
    h.qtbot.waitUntil(lambda: isinstance(popup.state, Failed), timeout=WAIT)
    assert popup.state == Failed(EXPECTED, "内部错误（ZeroDivisionError），详情见日志")
    assert "操作失败" in h.titles()
    assert clipboard.text() == SENTINEL


# --- LAST_RESULT (F10-1) ------------------------------------------------------------------------


@pytest.mark.parametrize("via", ["hotkey", "menu"])
def test_last_result_opens_the_window(make, via):
    h = make()
    window = h.controller.history_window
    if via == "hotkey":
        h.controller.handle_hotkey(hotkey_id(Command.LAST_RESULT))
    else:
        h.menu_action(Command.LAST_RESULT).trigger()
    assert window.isVisible()
    assert window.empty_label.isVisible()


def test_open_window_follows_new_results(make, clipboard):
    h = make()
    window = h.controller.history_window
    h.controller.run(Command.LAST_RESULT)
    h.controller.run(Command.OCR)
    h.select()
    h.qtbot.waitUntil(lambda: window.position_label.text() == "1 / 1", timeout=WAIT)
    assert window.text_view.toPlainText() == EXPECTED


# --- OPEN_CONFIG (F9) -----------------------------------------------------------------------------


def test_open_config_creates_missing_file_then_opens(make):
    h = make()
    assert not h.config_path.exists()
    h.controller.run(Command.OPEN_CONFIG)
    assert h.config_path.read_text(encoding="utf-8") == DEFAULT_TEMPLATE
    assert h.opened == [h.config_path]
    assert h.titles() == ["已打开配置文件"]
    assert "重启" in h.notifier.notices[0].body


def test_open_config_never_overwrites(make, tmp_path):
    path = tmp_path / "mine.toml"
    path.write_text("# mine\n", encoding="utf-8")
    h = make(config_path=path)
    h.menu_action(Command.OPEN_CONFIG).trigger()
    assert path.read_text(encoding="utf-8") == "# mine\n"
    assert h.opened == [path]


def test_open_config_creation_failure_is_reported(make, tmp_path):
    h = make(config_path=tmp_path / "no-such-dir" / "config.local.toml")
    h.controller.run(Command.OPEN_CONFIG)
    assert h.opened == []
    assert h.titles() == ["配置文件有 1 个问题"]


def test_open_config_open_failure_is_reported(make):
    h = make()
    h.open_error = OSError("no application is associated")
    h.controller.run(Command.OPEN_CONFIG)
    assert h.titles() == ["无法打开配置文件"]
    assert "no application is associated" in h.notifier.notices[0].body


# --- QUIT (F5-5) ---------------------------------------------------------------------------------


def test_quit_releases_everything(make):
    h = make()
    h.controller.run(Command.LAST_RESULT)
    h.controller.run(Command.CAPTURE)
    overlays = h.controller.overlays
    h.menu_action(Command.QUIT).trigger()
    assert h.table.ours == {}
    assert h.quits == [True]
    assert not h.controller.history_window.isVisible()
    assert not any(o.isVisible() for o in overlays)
    with pytest.raises(RuntimeError, match="shut down"):
        h.controller.runner.submit(lambda: iter(()))
    h.controller.run(Command.QUIT)
    assert h.quits == [True]


def test_quit_hides_the_popup(make):
    h = make()
    h.controller.run(Command.TRANSLATE)
    h.select()
    h.qtbot.waitUntil(lambda: isinstance(h.controller.popup.state, Done), timeout=WAIT)
    h.controller.run(Command.QUIT)
    assert not h.controller.popup.isVisible()


# --- added after the first green (coverage) ------------------------------------------------


def test_outcome_without_notice_changes_clipboard_silently(make, clipboard):
    from snapocr.actions.outcomes import ClipboardText, Outcome
    from snapocr.actions.runner import OcrDone

    h = make()
    h.controller.bridge.post(OcrDone(99, Outcome(ClipboardText("quiet"), None, None)))
    h.qtbot.waitUntil(lambda: clipboard.text() == "quiet", timeout=WAIT)
    assert h.notifier.notices == []


# --- WI-22: which hotkeys are live ------------------------------------------------------


def test_registered_commands_lists_live_hotkeys(make):
    h = make(preoccupy=["Alt+3"])
    assert h.controller.registered_commands() == (Command.CAPTURE, Command.OCR, Command.LAST_RESULT)
    h.controller.run(Command.QUIT)
    assert h.controller.registered_commands() == (Command.CAPTURE, Command.OCR, Command.LAST_RESULT)  # what start() got
