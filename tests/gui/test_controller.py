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
  start nothing new; they bring the open session back (M5 WI-2, F18-2). ``CaptureError`` -> "截图失败" notice, no session.
- Cancelled selection: no clipboard change, no notice (F6-3).
- CAPTURE: the PNG of the selection on the clipboard + "已复制截图" (F7-1).
- OCR / TRANSLATE are jobs; OcrDone -> clipboard + notice (F7-2 to F7-4);
  TranslateStarted -> popup Translating, placed next to the selection inside
  the screen's work area (logical; the screen's logical rect if none given);
  TranslateDone -> popup state and clipboard (F7-5, F8). Each finished job
  (The last-results window is gone since PRD v1.3, F19-8.)
- JobCrashed -> "操作失败" notice; a popup waiting on that job shows Failed.
- TRANSLATE_TEXT opens the translation window (F19-3; section at the end).
- OPEN_CONFIG: a missing file is first created from the template (never
  overwriting); then ``open_file(path)`` and "修改后重启 snapocr 生效".
  Creation failure -> config-issues notice and nothing opened; ``open_file``
  raising OSError -> "无法打开配置文件".
- QUIT: hotkeys released, runner shut down, session / popup / window
  closed, ``quit_app()`` called; a second QUIT does nothing more.
- SETTINGS (M3 WI-6, PRD F11): see the section at the end.
"""

import threading
from pathlib import Path

import pytest
from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QToolButton

from snapocr.actions.flows import FlowDeps
from snapocr.actions.messages import preview, screen_permission_notice
from snapocr.actions.outcomes import Done, Failed, Translating
from snapocr.annotate import DEFAULT_STYLE, PALETTE, Mark, Style, Tool
from snapocr.commands import Command
from snapocr.config.schema import AppConfig, ConfigIssue
from snapocr.config.template import DEFAULT_TEMPLATE
from snapocr.engines.errors import EngineLoadError
from snapocr.engines.holder import EngineHolder
from snapocr.engines.types import OcrResult
from snapocr.geometry import Rect, ScreenInfo, logical_rect, place_popup
from snapocr.gui.controller import AppController
from snapocr.gui.imageops import crop, decode_png
from snapocr.gui.marks_paint import render_marked
from snapocr.hotkeys import hotkey_id, parse_hotkey
from snapocr.postprocess import PostprocessOptions, Replacements, postprocess
from snapocr.translators.types import TranslationResult
from support import qt_input as qi
from support.fake_actions import ScriptedEngine, ScriptedTranslator, holder_for
from support.fake_desktop import FakeAutostart, FakeCapture, RecordingNotifier, desktop_image
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
                 capture_error=None, capture_denied=False, issues=(), preoccupy=(), config_path=None, make_translator=None,
                 autostart=None, list_models=None, show_text=True, debug=False, save_dir=None, glass=None,
                 theme="system"):
        self.capture = FakeCapture(desktop_image(1400, 600), (0, 0), (MAIN, SIDE), dict(WORK), capture_error,
                                   denied=capture_denied)
        self.notifier = RecordingNotifier()
        self.table = FakeHotkeyTable()
        for text in preoccupy:
            hk = parse_hotkey(text)
            self.table.preoccupy(hk.mods, hk.vk)
        self.opened: list[Path] = []
        self.open_error: OSError | None = None
        self.quits: list[bool] = []
        self.config_path = config_path or tmp_path / "config.local.toml"
        self.autostart = autostart or FakeAutostart()
        self.save_dir = save_dir or tmp_path / "shots"  # never the real Pictures folder (F17-2)
        config = AppConfig(replacements=TABLE, show_text=show_text, debug=debug, save_dir=self.save_dir, theme=theme)
        self.debug_dir = tmp_path / "debug"  # never the real D:\DevLocal\runtime\snapocr\debug
        deps = FlowDeps(holder or holder_for(engine, load_error=load_error), config.postprocess, config.replacements)
        self.controller = AppController(
            config,
            self.config_path,
            deps,
            make_translator=make_translator or (lambda cfg: translator or ScriptedTranslator()),
            list_models=list_models or (lambda cfg: ()),
            capture_provider=self.capture,
            notifier=self.notifier,
            hotkey_backend=self.table,
            autostart=self.autostart,
            open_file=self._open,
            quit_app=lambda: self.quits.append(True),
            startup_issues=list(issues),
            debug_dir=self.debug_dir,
            **({} if glass is None else {"glass": glass}),  # M7 WI-6
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
        labels = {Command.CAPTURE: "截图", Command.OCR: "OCR", Command.TRANSLATE: "截图翻译", Command.TRANSLATE_TEXT: "文字翻译",
                  Command.CODE_OCR: "代码 OCR", Command.TABLE_OCR: "表格 OCR", Command.SETTINGS: "设置…",
                  Command.QUIT: "退出"}
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
    assert sorted(h.table.ours) == sorted(hotkey_id(c) for c in (Command.CAPTURE, Command.OCR, Command.TRANSLATE, Command.TRANSLATE_TEXT,
                                                                 Command.CODE_OCR, Command.TABLE_OCR))
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


@pytest.mark.parametrize(
    "command", [Command.CAPTURE, Command.OCR, Command.TRANSLATE, Command.CODE_OCR, Command.TABLE_OCR]
)
def test_no_screen_recording_permission_is_its_own_notice(make, clipboard, command):
    """M9 WI-15 (F23-3): no overlay, clipboard kept, only the permission notice."""
    h = make(capture_error="no permission", capture_denied=True)
    h.controller.run(command)
    assert h.controller.overlays == ()
    assert h.notifier.notices == [screen_permission_notice()]
    assert clipboard.text() == SENTINEL
    assert h.capture.taken == []


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
    via_hotkey = (clipboard.text(), h.titles()[-1])
    clipboard.setText(SENTINEL)
    h.menu_action(Command.OCR).trigger()
    assert h.controller.overlays == ()  # deferred until the menu has closed
    h.qtbot.waitUntil(lambda: len(h.controller.overlays) == 2, timeout=WAIT)
    h.select()
    h.qtbot.waitUntil(lambda: clipboard.text() == EXPECTED, timeout=WAIT)
    assert (clipboard.text(), h.titles()[-1]) == via_hotkey
    assert len(h.titles()) == 2


# --- CODE OCR (M3 WI-14, PRD F13-1) ----------------------------------------------------------

CODE_RESULT = OcrResult((rect("def f():", 0, 0, 80, 20), rect("return 0CR", 40, 30, 140, 50)))
CODE = "def f():\n    return 0CR"  # indentation kept, no replacement table


def test_code_ocr_hotkey_puts_code_text_on_clipboard(make, clipboard):
    h = make(engine=CODE_RESULT)
    h.controller.handle_hotkey(hotkey_id(Command.CODE_OCR))
    h.select()
    h.qtbot.waitUntil(lambda: clipboard.text() == CODE, timeout=WAIT)
    h.qtbot.waitUntil(lambda: h.titles() == ["已复制代码"], timeout=WAIT)
    assert h.notifier.notices[0].body == preview(CODE)


def test_code_ocr_from_the_menu(make, clipboard):
    h = make(engine=CODE_RESULT)
    h.menu_action(Command.CODE_OCR).trigger()
    h.qtbot.waitUntil(lambda: len(h.controller.overlays) == 2, timeout=WAIT)
    h.select()
    h.qtbot.waitUntil(lambda: clipboard.text() == CODE, timeout=WAIT)


def test_code_ocr_empty_keeps_the_clipboard(make, clipboard):
    h = make(engine=OcrResult(()))
    h.controller.run(Command.CODE_OCR)
    h.select()
    h.qtbot.waitUntil(lambda: h.titles() == ["未识别到文字"], timeout=WAIT)
    assert clipboard.text() == SENTINEL


# --- TABLE OCR (M4 WI-15, PRD F16-1, F16-2) ----------------------------------------------------

TABLE_RESULT = OcrResult((
    rect("Name", 0, 0, 60, 20), rect("Qty", 200, 0, 240, 20),
    rect("Pear", 0, 30, 50, 50), rect("12", 215, 30, 235, 50),
))
TABLE_MD = "| Name | Qty |\n| --- | --- |\n| Pear | 12 |"


def test_table_ocr_hotkey_puts_the_table_on_clipboard(make, clipboard):
    h = make(engine=TABLE_RESULT)
    h.controller.handle_hotkey(hotkey_id(Command.TABLE_OCR))
    h.select()
    h.qtbot.waitUntil(lambda: clipboard.text() == TABLE_MD, timeout=WAIT)
    assert "<td>Pear</td><td>12</td>" in clipboard.mimeData().html()
    h.qtbot.waitUntil(lambda: h.titles() == ["已复制表格"], timeout=WAIT)
    assert h.notifier.notices[0].body == "2 行 × 2 列"


def test_table_ocr_from_the_menu(make, clipboard):
    h = make(engine=TABLE_RESULT)
    h.menu_action(Command.TABLE_OCR).trigger()
    h.qtbot.waitUntil(lambda: len(h.controller.overlays) == 2, timeout=WAIT)
    h.select()
    h.qtbot.waitUntil(lambda: clipboard.text() == TABLE_MD, timeout=WAIT)


# --- TRANSLATE (F7-5, F8) ---------------------------------------------------------------------


class GatedTranslator:
    def __init__(self):
        self.gate = threading.Event()

    def translate(self, text, target=None):
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
    h.controller.run(Command.OPEN_CONFIG)
    assert path.read_text(encoding="utf-8") == "# mine\n"
    assert h.opened == [path]


def test_open_config_creation_failure_is_reported(make, tmp_path):
    (tmp_path / "blocker").write_text("x", encoding="utf-8")  # a file where the directory should be
    h = make(config_path=tmp_path / "blocker" / "config.local.toml")
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
    h.controller.run(Command.TRANSLATE_TEXT)
    h.controller.run(Command.CAPTURE)
    overlays = h.controller.overlays
    h.menu_action(Command.QUIT).trigger()
    assert h.table.ours == {}
    assert h.quits == [True]
    assert not h.controller.popup.isVisible()
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
    live = (Command.CAPTURE, Command.OCR, Command.TRANSLATE_TEXT, Command.CODE_OCR, Command.TABLE_OCR)
    assert h.controller.registered_commands() == live
    h.controller.run(Command.QUIT)
    assert h.controller.registered_commands() == live  # what start() got



# --- SETTINGS (M3 WI-6, PRD F11-1, F11-3, F11-5) --------------------------------------------------
#
# Pinned here (beyond the plan text):
# - Opening releases every hotkey of ours; while the window is open no hotkey
#   is registered. Opening again while it is open only raises it (values
#   being edited are kept).
# - Cancel / close re-registers the bindings from before; a failure then is
#   reported like at start-up (F5-3).
# - Save order and rollback follow plan D11. On any problem the window stays
#   open with the problem text, none of our hotkeys is registered, the file
#   and start-at-login are as before.
# - Save with nothing changed writes no file.
# - A successful save shows one notice "设置已保存" and closes the window
#   without registering the hotkeys a second time.

from snapocr.config.files import load_config_file  # noqa: E402
from snapocr.config.settings import settings_of  # noqa: E402
from snapocr.hotkeys import MOD_NOREPEAT  # noqa: E402
from PySide6.QtCore import QEvent  # noqa: E402
from PySide6.QtGui import QKeyEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

M = Qt.KeyboardModifier
DEFAULT_IDS = sorted(hotkey_id(c) for c in (Command.CAPTURE, Command.OCR, Command.TRANSLATE, Command.TRANSLATE_TEXT,
                                           Command.CODE_OCR, Command.TABLE_OCR))


def record(edit, key, mods):
    for kind in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
        QApplication.sendEvent(edit, QKeyEvent(kind, key, mods))


def combo(text):
    hk = parse_hotkey(text)
    return (hk.mods | MOD_NOREPEAT, hk.vk)


def model_translator(cfg):
    """A translator whose output names the config it was built from."""
    return ScriptedTranslator(TranslationResult(f"{cfg.model}/{cfg.target_lang}", "en", False))


def open_settings(h):
    h.controller.run(Command.SETTINGS)
    window = h.controller.settings_window
    h.qtbot.waitExposed(window)
    return window


def edit_and_save(h, window, *, capture="Ctrl+Q"):
    record(window.hotkey_edits[Command.CAPTURE], getattr(Qt.Key, f"Key_{capture[-1]}"), M.ControlModifier)
    assert window.hotkey_edits[Command.CAPTURE].text() == capture
    window.switch_boxes["spacing"].setChecked(False)
    window.target_lang_box.setCurrentIndex(window.target_lang_box.findData("zh"))
    window.model_edit.setText("qwen3:8b")
    window.autostart_box.setChecked(True)
    window.save_button.click()


def test_menu_opens_settings_with_current_values(make):
    h = make(autostart=FakeAutostart(enabled=True))
    h.menu_action(Command.SETTINGS).trigger()
    window = h.controller.settings_window
    h.qtbot.waitUntil(window.isVisible)
    assert [window.hotkey_edits[c].text() for c in (Command.CAPTURE, Command.OCR, Command.TRANSLATE,
                                                    Command.TRANSLATE_TEXT)] == ["Alt+1", "Alt+2", "Alt+3", "Alt+4"]
    assert window.hotkey_edits[Command.CODE_OCR].text() == "Alt+5"  # M3 WI-14
    assert window.hotkey_edits[Command.TABLE_OCR].text() == "Alt+6"  # M4 WI-15
    assert window.autostart_box.isChecked()
    assert window.model_edit.text() == "hy-mt2:7b"
    assert window.target_lang_box.currentData() == "auto"


def test_hotkeys_paused_while_open(make):
    h = make()
    open_settings(h)
    assert h.table.ours == {}
    h.controller.handle_hotkey(hotkey_id(Command.CAPTURE))
    assert h.controller.overlays == ()


def test_open_again_keeps_edits(make):
    h = make()
    window = open_settings(h)
    window.model_edit.setText("editing")
    h.controller.run(Command.SETTINGS)
    assert window.isVisible()
    assert window.model_edit.text() == "editing"
    assert h.table.ours == {}


def test_autostart_read_error_shows_unchecked(make):
    h = make(autostart=FakeAutostart(enabled=True, read_error=PermissionError(5, "denied")))
    window = open_settings(h)
    assert not window.autostart_box.isChecked()


def test_cancel_restores_hotkeys_and_changes_nothing(make):
    h = make()
    before = h.table.snapshot()
    window = open_settings(h)
    window.model_edit.setText("qwen3:8b")
    window.cancel_button.click()
    assert not window.isVisible()
    assert h.table.snapshot() == before
    assert not h.config_path.exists()
    assert h.notifier.notices == []
    h.controller.handle_hotkey(hotkey_id(Command.CAPTURE))
    assert len(h.controller.overlays) == 2


def test_cancel_reports_hotkey_taken_meanwhile(make):
    h = make()
    window = open_settings(h)
    hk = parse_hotkey("Alt+2")
    h.table.preoccupy(hk.mods, hk.vk)
    window.close()
    assert h.titles() == ["有 1 个热键注册失败"]
    assert sorted(h.table.ours) == [i for i in DEFAULT_IDS if i != hotkey_id(Command.OCR)]


def test_save_applies_everything(make, clipboard):
    h = make(make_translator=model_translator)
    window = open_settings(h)
    edit_and_save(h, window)
    assert not window.isVisible()
    assert h.titles() == ["设置已保存"]
    assert sorted(h.table.ours) == DEFAULT_IDS
    assert h.table.ours[hotkey_id(Command.CAPTURE)] == combo("Ctrl+Q")
    assert h.menu_action(Command.CAPTURE).text() == "截图\tCtrl+Q"
    assert h.autostart.enabled is True
    loaded = load_config_file(h.config_path)
    assert loaded.issues == []
    s = settings_of(loaded.config)
    assert (s.hotkeys[Command.CAPTURE], s.spacing, s.target_lang, s.model) == (
        parse_hotkey("Ctrl+Q"), False, "zh", "qwen3:8b")
    assert loaded.config.replacements == Replacements.EMPTY  # the file never had the harness's table


def test_after_save_new_hotkey_and_options_are_used(make, clipboard):
    h = make(make_translator=model_translator)
    edit_and_save(h, open_settings(h))
    h.controller.handle_hotkey(hotkey_id(Command.OCR))
    h.select()
    expected = postprocess(RESULT, PostprocessOptions(spacing=False), TABLE)
    h.qtbot.waitUntil(lambda: clipboard.text() == expected, timeout=WAIT)
    h.controller.handle_hotkey(hotkey_id(Command.TRANSLATE))
    h.select()
    h.qtbot.waitUntil(lambda: clipboard.text() == "qwen3:8b/zh", timeout=WAIT)


def test_save_with_duplicate_hotkeys_is_refused(make):
    h = make()
    window = open_settings(h)
    record(window.hotkey_edits[Command.OCR], Qt.Key.Key_1, M.AltModifier)
    window.save_button.click()
    assert window.isVisible()
    assert window.problems_label.text() == "「截图」和「OCR」用了同一个热键 Alt+1。"
    assert h.table.ours == {}
    assert not h.config_path.exists()
    assert h.notifier.notices == []


def test_save_with_bad_model_is_refused(make):
    h = make()
    window = open_settings(h)
    window.model_edit.setText("gpt-oss:120b-cloud")
    window.save_button.click()
    assert window.isVisible()
    assert window.problems_label.text().startswith("模型名不能用：")
    assert not h.config_path.exists()


def test_save_with_taken_hotkey_is_refused_and_cancel_restores(make):
    h = make()
    before = h.table.snapshot()
    hk = parse_hotkey("Ctrl+Q")
    h.table.preoccupy(hk.mods, hk.vk)
    window = open_settings(h)
    edit_and_save(h, window)
    assert window.isVisible()
    assert window.problems_label.text() == "Ctrl+Q（截图）：已被其他软件占用"
    assert h.table.ours == {}
    assert h.autostart.enabled is False
    assert not h.config_path.exists()
    window.cancel_button.click()
    assert {k: v for k, v in h.table.snapshot().items() if v != "other program"} == before


def test_autostart_failure_is_refused(make):
    h = make(autostart=FakeAutostart(set_errors=[PermissionError(5, "Access is denied")]))
    window = open_settings(h)
    edit_and_save(h, window)
    assert window.isVisible()
    assert window.problems_label.text() == "无法设置开机自启动：Access is denied"
    assert h.table.ours == {}
    assert not h.config_path.exists()


def test_file_failure_rolls_back_autostart(make, tmp_path):
    path = tmp_path / "broken.toml"
    path.write_text("[postprocess\n", encoding="utf-8")
    h = make(config_path=path)
    window = open_settings(h)
    edit_and_save(h, window)
    assert window.isVisible()
    assert "语法错误" in window.problems_label.text()
    assert h.autostart.enabled is False
    assert h.table.ours == {}
    assert path.read_text(encoding="utf-8") == "[postprocess\n"


def test_failed_rollback_still_reports_the_file_problem(make, tmp_path):
    path = tmp_path / "broken.toml"
    path.write_text("[postprocess\n", encoding="utf-8")
    h = make(config_path=path, autostart=FakeAutostart(set_errors=[None, PermissionError(5, "denied")]))
    window = open_settings(h)
    edit_and_save(h, window)
    assert "语法错误" in window.problems_label.text()
    assert h.autostart.enabled is True  # the rollback failed; the window says what went wrong with the file


def test_save_without_changes_writes_nothing(make):
    h = make()
    window = open_settings(h)
    window.save_button.click()
    assert not window.isVisible()
    assert not h.config_path.exists()
    assert h.titles() == ["设置已保存"]
    assert sorted(h.table.ours) == DEFAULT_IDS


def test_advanced_opens_config_file(make):
    h = make()
    window = open_settings(h)
    window.advanced_button.click()
    assert h.opened == [h.config_path]
    assert h.titles() == ["已打开配置文件"]
    assert window.isVisible()


def test_quit_while_settings_open(make):
    h = make()
    window = open_settings(h)
    h.controller.run(Command.QUIT)
    assert not window.isVisible()
    assert h.table.ours == {}
    assert h.quits == [True]
    assert h.notifier.notices == []


def test_file_failure_without_autostart_change(make, tmp_path):
    path = tmp_path / "broken.toml"
    path.write_bytes(b"\xff")
    h = make(config_path=path, autostart=FakeAutostart(enabled=True))
    window = open_settings(h)
    window.model_edit.setText("qwen3:8b")
    window.save_button.click()
    assert "UTF-8" in window.problems_label.text()
    assert h.autostart.enabled is True
    assert path.read_bytes() == b"\xff"


# --- M3 WI-10: model list in the settings window (F11-7, plan D12, D14) ---------------------
# The list is read on a background thread; the window opens at once with a "loading" hint.

from snapocr.actions.messages import MODELS_LOADING  # noqa: E402
from snapocr.translators.errors import TranslationError, TranslationErrorKind  # noqa: E402


class ModelLister:
    """``list_models`` stand-in; ``hold()`` makes calls wait until ``release()``."""

    def __init__(self, result):
        self.result = result
        self.asked = []
        self.gate = threading.Event()
        self.gate.set()

    def hold(self):
        self.gate.clear()

    def release(self):
        self.gate.set()

    def __call__(self, config):
        self.asked.append((config.base_url, config.model))
        assert self.gate.wait(5)
        result = self.result(len(self.asked)) if callable(self.result) else self.result
        if isinstance(result, BaseException):
            raise result
        return result


def model_items(window):
    return [window.model_box.itemText(i) for i in range(window.model_box.count())]


def test_settings_open_at_once_and_fill_the_list_later(make):
    lister = ModelLister(("hy-mt2:7b", "qwen3:8b"))
    lister.hold()
    h = make(list_models=lister)
    window = open_settings(h)
    assert MODELS_LOADING == "正在读取模型列表…"
    assert window.models_hint.isVisible() and window.models_hint.text() == MODELS_LOADING
    assert model_items(window) == ["hy-mt2:7b"]
    lister.release()
    h.qtbot.waitUntil(lambda: model_items(window) == ["hy-mt2:7b", "qwen3:8b"], timeout=WAIT)
    assert lister.asked == [("http://127.0.0.1:11434", "hy-mt2:7b")]
    assert window.model_box.currentText() == "hy-mt2:7b"
    assert not window.models_hint.isVisible()


def test_settings_model_list_failure_shows_a_hint(make):
    err = TranslationError(TranslationErrorKind.UNREACHABLE, base_url="http://127.0.0.1:11434", model="hy-mt2:7b")
    h = make(list_models=ModelLister(err))
    window = open_settings(h)
    hint = "没能读取模型列表（翻译服务没有运行），可以直接输入模型名。"
    h.qtbot.waitUntil(lambda: window.models_hint.text() == hint, timeout=WAIT)
    assert window.models_hint.isVisible()
    assert model_items(window) == ["hy-mt2:7b"]


def test_settings_asks_again_with_the_saved_model(make):
    lister = ModelLister(("hy-mt2:7b", "qwen3:8b"))
    h = make(list_models=lister)
    window = open_settings(h)
    h.qtbot.waitUntil(lambda: model_items(window) == ["hy-mt2:7b", "qwen3:8b"], timeout=WAIT)
    window.model_box.setCurrentIndex(model_items(window).index("qwen3:8b"))
    window.save_button.click()
    assert not window.isVisible()
    open_settings(h)
    h.qtbot.waitUntil(lambda: len(lister.asked) == 2, timeout=WAIT)
    assert lister.asked == [("http://127.0.0.1:11434", "hy-mt2:7b"), ("http://127.0.0.1:11434", "qwen3:8b")]


def test_open_again_while_visible_does_not_ask_again(make):
    lister = ModelLister(("hy-mt2:7b",))
    h = make(list_models=lister)
    window = open_settings(h)
    h.qtbot.waitUntil(lambda: not window.models_hint.isVisible(), timeout=WAIT)
    h.controller.run(Command.SETTINGS)
    h.qtbot.wait(100)
    assert len(lister.asked) == 1


def test_a_late_list_from_an_earlier_opening_is_ignored(make):
    lister = ModelLister(lambda n: ("old-model",) if n == 1 else ("hy-mt2:7b", "new-model"))
    lister.hold()
    h = make(list_models=lister)
    window = open_settings(h)
    window.close()
    open_settings(h)  # the second request also waits on the gate
    lister.release()
    h.qtbot.waitUntil(lambda: model_items(window) == ["hy-mt2:7b", "new-model"], timeout=WAIT)
    h.qtbot.wait(200)
    assert "old-model" not in model_items(window)


def test_a_list_arriving_after_the_controller_is_deleted_is_dropped(make):
    # Real shutdown deletes the controller (and its bridge) while the thread may still wait on the service.
    import shiboken6

    errors = []
    previous, threading.excepthook = threading.excepthook, errors.append
    try:
        lister = ModelLister(("hy-mt2:7b",))
        lister.hold()
        h = make(list_models=lister)
        open_settings(h)
        shiboken6.delete(h.controller.bridge)
        lister.release()
        h.qtbot.waitUntil(lambda: not any(t.name == "snapocr-models" for t in threading.enumerate()), timeout=WAIT)
    finally:
        threading.excepthook = previous
    assert errors == []


# --- M3 WI-11: OCR notice without the text (F7-2, F11-8) ----------------------------------


def test_ocr_notice_without_text_after_unticking_the_switch(make, clipboard):
    h = make()
    window = open_settings(h)
    window.show_text_box.setChecked(False)
    window.save_button.click()
    assert not window.isVisible()
    assert load_config_file(h.config_path).config.show_text is False
    h.controller.handle_hotkey(hotkey_id(Command.OCR))
    h.select()
    h.qtbot.waitUntil(lambda: clipboard.text() == EXPECTED, timeout=WAIT)
    h.qtbot.waitUntil(lambda: "已复制 OCR 文本" in h.titles(), timeout=WAIT)
    notice = next(n for n in h.notifier.notices if n.title == "已复制 OCR 文本")
    assert notice.body == f"共 {len(''.join(EXPECTED.split()))} 个字"


def test_controller_takes_show_text_from_the_config(make, clipboard):
    h = make(show_text=False)
    h.controller.run(Command.OCR)
    h.select()
    h.qtbot.waitUntil(lambda: h.titles() == ["已复制 OCR 文本"], timeout=WAIT)
    assert h.notifier.notices[0].body == f"共 {len(''.join(EXPECTED.split()))} 个字"


# --- M3 WI-12: debug mode (F12) ----------------------------------------------------------

from snapocr.actions.debug import DEBUG_DIR, debug_text  # noqa: E402


def debug_files(h):
    return sorted(p.name for p in h.debug_dir.iterdir()) if h.debug_dir.exists() else []


def test_debug_on_reminds_at_start_and_saves_each_result(make, clipboard):
    h = make(debug=True)
    assert h.titles() == ["debug 模式已开启"]
    assert h.notifier.notices[0].body == f"截图和识别全文会保存到：{h.debug_dir}"
    h.controller.run(Command.OCR)
    h.select()
    h.qtbot.waitUntil(lambda: len(debug_files(h)) == 2, timeout=WAIT)
    png_name, txt_name = debug_files(h)
    assert png_name.endswith("-2.png") and txt_name == png_name[:-4] + ".txt"  # job 1 is the warm-up
    # The last-results history that held the record is gone (F19-8): check the files themselves.
    shot = decode_png((h.debug_dir / png_name).read_bytes())
    assert (shot.width(), shot.height()) == (100, 60)
    text = (h.debug_dir / txt_name).read_text(encoding="utf-8")
    assert text.startswith("## OCR 原文\n") and f"## 后处理文本\n{EXPECTED}\n" in text


def test_debug_saves_translations_too(make, clipboard):
    h = make(debug=True)
    h.controller.run(Command.TRANSLATE)
    h.select()
    h.qtbot.waitUntil(lambda: len(debug_files(h)) == 2, timeout=WAIT)
    text = (h.debug_dir / debug_files(h)[1]).read_text(encoding="utf-8")
    assert "## 译文" in text


def test_debug_off_writes_nothing_and_says_nothing(make, clipboard):
    h = make()
    assert h.notifier.notices == []
    h.controller.run(Command.OCR)
    h.select()
    h.qtbot.waitUntil(lambda: clipboard.text() == EXPECTED, timeout=WAIT)
    h.qtbot.wait(100)
    assert not h.debug_dir.exists()


def test_the_real_debug_directory_is_the_default():
    import inspect

    assert inspect.signature(AppController).parameters["debug_dir"].default == DEBUG_DIR


# --- M4 WI-6: annotation on the capture action (PRD F14-1, F14-4, F14-7; plan D13) -----------------
#
# Pinned here:
# - Only CAPTURE opens overlays in annotation mode (each has a toolbar); OCR,
#   TRANSLATE and CODE_OCR overlays have none.
# - Confirming a capture with marks puts ``render_marked(crop, marks, selection
#   origin)`` on the clipboard: the marks of the confirmed overlay, in physical px.
# - The last style picked on any capture toolbar is the starting style of the
#   next capture (memory only); it starts as DEFAULT_STYLE.


def annotate_tb(overlay, name):
    assert overlay.toolbar is not None, "no toolbar"
    found = overlay.toolbar.findChild(QToolButton, name)
    assert found is not None, name
    return found


def test_only_capture_overlays_have_a_toolbar(make):
    h = make()
    h.controller.run(Command.CAPTURE)
    assert all(o.toolbar is not None for o in h.controller.overlays)
    qi.key(h.controller.overlays[0], Qt.Key.Key_Escape)
    for command in (Command.OCR, Command.TRANSLATE, Command.CODE_OCR, Command.TABLE_OCR):
        h.controller.run(command)
        assert all(o.toolbar is None for o in h.controller.overlays), command
        qi.key(h.controller.overlays[0], Qt.Key.Key_Escape)


def test_capture_with_marks_puts_the_marked_image_on_clipboard(make, clipboard):
    h = make()
    h.controller.run(Command.CAPTURE)
    overlay = h.controller.overlays[0]
    qi.drag(overlay, 10, 20, 210, 170)
    annotate_tb(overlay, "tool-rect").click()
    qi.drag(overlay, 30, 40, 120, 100)
    qi.key(overlay, Qt.Key.Key_Return)
    marks = (Mark(Tool.RECT, ((30, 40), (120, 100)), PALETTE[0], 4),)
    expected = render_marked(crop(h.capture.image, Rect(10, 20, 200, 150)), marks, (10, 20))
    got = decode_png(bytes(clipboard.mimeData().data("image/png")))
    assert pixels(got) == pixels(expected)
    assert got.pixelColor(20, 50).name() == PALETTE[0]  # the left edge at physical (30, 70)
    assert h.titles() == ["已复制截图"]


def test_capture_with_marks_on_the_scaled_screen(make, clipboard):
    h = make()
    h.controller.run(Command.CAPTURE)
    overlay = h.controller.overlays[1]
    qi.drag(overlay, 10, 10, 110, 60)
    annotate_tb(overlay, "tool-arrow").click()
    qi.drag(overlay, 20, 20, 100, 50)
    marks = overlay.marks
    assert marks and marks[0].size == 6  # 4 logical px at 150%
    qi.key(overlay, Qt.Key.Key_Return)
    expected = render_marked(crop(h.capture.image, Rect(815, 15, 150, 75)), marks, (815, 15))
    assert pixels(decode_png(bytes(clipboard.mimeData().data("image/png")))) == pixels(expected)


def test_style_is_remembered_between_captures(make):
    h = make()
    h.controller.run(Command.CAPTURE)
    assert all(o.toolbar.style == DEFAULT_STYLE for o in h.controller.overlays)
    overlay = h.controller.overlays[1]
    qi.drag(overlay, 10, 10, 110, 60)
    annotate_tb(overlay, "color-4").click()
    annotate_tb(overlay, "level-2").click()
    qi.key(overlay, Qt.Key.Key_Escape)
    h.controller.run(Command.OCR)
    qi.key(h.controller.overlays[0], Qt.Key.Key_Escape)
    h.controller.run(Command.CAPTURE)
    assert all(o.toolbar.style == Style(PALETTE[4], 2) for o in h.controller.overlays)


# --- M4 WI-8: pinning a capture (PRD F15-1, F15-3; plan D14) --------------------------------------
#
# Pinned here:
# - The toolbar's pin button turns the selection (with its marks) into a
#   ``PinWindow`` at the selection's logical rect on its screen
#   (``logical_rect``), shown; the clipboard does not change and no notice is
#   shown. ``controller.pins`` lists the open pin windows.
# - Several pins can be open; a closed pin leaves ``pins``; QUIT closes all.


def pin_capture(h, screen=0, area=(10, 20, 210, 170), mark=None):
    assert hasattr(h.controller, "pins"), "no pins"
    h.controller.run(Command.CAPTURE)
    overlay = h.controller.overlays[screen]
    qi.drag(overlay, *area)
    if mark is not None:
        annotate_tb(overlay, "tool-rect").click()
        qi.drag(overlay, *mark)
    annotate_tb(overlay, "pin").click()


def test_pin_opens_a_window_at_the_selection(make, clipboard):
    h = make()
    pin_capture(h, mark=(30, 40, 120, 100))
    (pin,) = h.controller.pins
    assert pin.isVisible()
    g = pin.geometry()
    assert Rect(g.x(), g.y(), g.width(), g.height()) == logical_rect(MAIN, Rect(10, 20, 200, 150))
    marks = (Mark(Tool.RECT, ((30, 40), (120, 100)), PALETTE[0], 4),)
    expected = render_marked(crop(h.capture.image, Rect(10, 20, 200, 150)), marks, (10, 20))
    assert pixels(pin.image) == pixels(expected)
    assert clipboard.text() == SENTINEL
    assert h.notifier.notices == []
    assert h.controller.overlays == ()


def test_pin_on_the_scaled_screen(make):
    h = make()
    pin_capture(h, screen=1, area=(10, 10, 110, 60))
    (pin,) = h.controller.pins
    g = pin.geometry()
    assert Rect(g.x(), g.y(), g.width(), g.height()) == logical_rect(SIDE, Rect(815, 15, 150, 75))
    assert (pin.image.width(), pin.image.height()) == (150, 75)


def test_several_pins_and_closing_one(make):
    h = make()
    pin_capture(h)
    pin_capture(h, area=(300, 300, 400, 380))
    first, second = h.controller.pins
    first.close()
    assert h.controller.pins == (second,)
    assert second.isVisible()


def test_quit_closes_all_pins(make):
    h = make()
    pin_capture(h)
    pin_capture(h, area=(300, 300, 400, 380))
    pins = h.controller.pins
    h.controller.run(Command.QUIT)
    assert h.controller.pins == ()
    assert not any(p.isVisible() for p in pins)


# --- M4 WI-24: the save folder in the settings window (PRD F17-2) ---------------------------------
#
# Pinned here:
# - The window opens with the configured folder; saving it unchanged writes
#   nothing (``test_save_without_changes_writes_nothing`` with the harness's
#   non-default folder).
# - A new absolute folder is written to ``[capture] save_dir`` and applied.
# - A relative one is refused with the problem text; nothing is written.


def test_settings_show_the_save_dir(make):
    h = make()
    window = open_settings(h)
    assert window.save_dir_edit.text() == str(h.save_dir)


def test_new_save_dir_is_written_and_applied(make, tmp_path):
    h = make()
    window = open_settings(h)
    window.save_dir_edit.setText(str(tmp_path / "new shots"))
    window.save_button.click()
    assert h.titles() == ["设置已保存"]
    assert load_config_file(h.config_path).config.save_dir == tmp_path / "new shots"
    assert open_settings(h).save_dir_edit.text() == str(tmp_path / "new shots")


def test_relative_save_dir_is_refused(make):
    h = make()
    window = open_settings(h)
    window.save_dir_edit.setText("shots")
    window.save_button.click()
    assert window.isVisible()
    assert window.problems_label.text() == "「截图保存到」必须是完整的文件夹路径，例如 D:/截图。"
    assert not h.config_path.exists()
    assert h.titles() == []


# --- M4 WI-23, WI-26: saving a capture (PRD v1.1 F17-1, F17-2, F17-4, F17-5; plan D26, D28) ---------
#
# Pinned here:
# - The toolbar's save button (or Ctrl+S) opens the overlay's save-as dialog,
#   preset to ``snapocr_YYYYMMDD_HHMMSS.png`` in ``config.save_dir`` (created
#   when missing). Picking a file writes the selection with its marks as a PNG
#   there, puts the same PNG on the clipboard and shows no notice (PRD v1.1).
#   Another folder picked in the dialog does not
#   change the save folder setting.
# - Cancelling the dialog writes nothing and keeps the capture going.
# - A failed save still puts the PNG on the clipboard and shows "保存失败".

import re  # noqa: E402

from snapocr.gui.overlay import OverlayState  # noqa: E402

SAVED_NAME = re.compile(r"snapocr_\d{8}_\d{6}(_\d+)?\.png")


def saved_files(folder):
    """The PNGs in ``folder``; empty (not an error) while it does not exist."""
    return sorted(folder.glob("*.png"))


def save_capture(h, area=(10, 20, 210, 170), mark=None, *, key=False):
    h.controller.run(Command.CAPTURE)
    overlay = h.controller.overlays[0]
    qi.drag(overlay, *area)
    if mark is not None:
        annotate_tb(overlay, "tool-rect").click()
        qi.drag(overlay, *mark)
    if key:
        mod = Qt.KeyboardModifier.ControlModifier
        QApplication.sendEvent(overlay, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_S, mod, "\x13"))
    else:
        annotate_tb(overlay, "save").click()
    dialog = getattr(overlay, "save_dialog", None)
    assert dialog is not None and dialog.isVisible(), "no save dialog"
    return overlay, dialog


def save_capture_to(h, path=None, **kwargs):
    """Save a capture, picking ``path`` in the dialog, or else its preset file."""
    overlay, dialog = save_capture(h, **kwargs)
    dialog.fileSelected.emit(str(path) if path is not None else dialog.selectedFiles()[0])
    return overlay


def test_the_dialog_is_preset_in_the_save_folder(make):
    h = make()
    assert not h.save_dir.exists()
    _, dialog = save_capture(h)
    (preset,) = (Path(f) for f in dialog.selectedFiles())
    assert preset.parent == h.save_dir
    assert SAVED_NAME.fullmatch(preset.name), preset.name
    assert h.save_dir.is_dir()
    assert saved_files(h.save_dir) == []


def test_cancelling_the_dialog_writes_nothing(make, clipboard):
    clipboard.setText("before")
    h = make()
    overlay, dialog = save_capture(h)
    dialog.reject()
    assert saved_files(h.save_dir) == []
    assert clipboard.text() == "before"
    assert h.controller.overlays[0] is overlay
    assert len(h.controller.overlays) == 2  # both screens still up
    assert overlay.state is OverlayState.ADJUSTING
    assert h.titles() == []


def test_another_folder_picked_in_the_dialog(make, tmp_path):
    h = make()
    other = tmp_path / "elsewhere"
    other.mkdir()
    save_capture_to(h, other / "named by me.png")
    assert (other / "named by me.png").is_file()
    assert saved_files(h.save_dir) == []
    _, dialog = save_capture(h)
    assert Path(dialog.selectedFiles()[0]).parent == h.save_dir


def test_save_writes_the_marked_png_and_copies_it(make, clipboard):
    h = make()
    save_capture_to(h, mark=(30, 40, 120, 100))
    (path,) = saved_files(h.save_dir)
    assert SAVED_NAME.fullmatch(path.name), path.name
    marks = (Mark(Tool.RECT, ((30, 40), (120, 100)), PALETTE[0], 4),)
    expected = render_marked(crop(h.capture.image, Rect(10, 20, 200, 150)), marks, (10, 20))
    assert pixels(decode_png(path.read_bytes())) == pixels(expected)
    assert bytes(clipboard.mimeData().data("image/png")) == path.read_bytes()
    assert h.notifier.notices == []  # PRD v1.1: no notice on success
    assert h.controller.overlays == ()


def test_ctrl_s_saves_too(make, clipboard):
    h = make()
    save_capture_to(h, key=True)
    (path,) = saved_files(h.save_dir)
    assert pixels(decode_png(path.read_bytes())) == pixels(crop(h.capture.image, Rect(10, 20, 200, 150)))
    assert h.titles() == []


def test_two_saves_keep_both_files(make):
    h = make()
    save_capture_to(h)
    save_capture_to(h, area=(300, 300, 400, 380))
    assert len(saved_files(h.save_dir)) == 2
    assert h.titles() == []


@pytest.mark.windows  # takes the dialog's preset; Qt's non-native dialog on a Mac mangles it when the folder is missing
def test_failed_save_still_copies(make, clipboard, tmp_path):
    blocker = tmp_path / "taken"
    blocker.write_bytes(b"a file, not a folder")
    h = make(save_dir=blocker / "shots")
    save_capture_to(h)
    assert decode_png(bytes(clipboard.mimeData().data("image/png"))).size().toTuple() == (200, 150)
    (notice,) = h.notifier.notices
    assert notice.title == "保存失败"
    assert str(blocker / "shots") in notice.body
    assert blocker.read_bytes() == b"a file, not a folder"


def test_failed_save_to_a_picked_file_still_copies(make, clipboard, tmp_path):
    """M9 WI-1: the same failure on any system, with the file picked in the dialog."""
    blocker = tmp_path / "taken"
    blocker.write_bytes(b"a file, not a folder")
    target = blocker / "shots" / "snap.png"
    h = make(save_dir=tmp_path / "shots")
    save_capture_to(h, target)
    assert decode_png(bytes(clipboard.mimeData().data("image/png"))).size().toTuple() == (200, 150)
    (notice,) = h.notifier.notices
    assert notice.title == "保存失败" and notice.warning
    assert notice.body.endswith(f"\n{target}")
    assert blocker.read_bytes() == b"a file, not a folder"
    assert h.controller.overlays == ()


def test_ocr_overlay_has_no_save(make):
    h = make()
    h.controller.run(Command.OCR)
    assert h.controller.overlays[0].toolbar is None


def test_save_goes_to_the_folder_set_in_the_settings_window(make, tmp_path):
    h = make()
    window = open_settings(h)
    window.save_dir_edit.setText(str(tmp_path / "chosen"))
    window.save_button.click()
    save_capture_to(h)
    assert len(saved_files(tmp_path / "chosen")) == 1
    assert saved_files(h.save_dir) == []


# --- M5 WI-2: a capture command while the overlay is open brings it back (PRD F18-2) -----------
# Pinned: no new capture, no new overlays. The overlay with a selection (else the
# first one) becomes the active window, or its save dialog when that is open.
# Selection, marks and tool stay; Enter still finishes the capture.

import pytestqt.exceptions  # noqa: E402
from PySide6.QtWidgets import QWidget  # noqa: E402


def steal_focus(qtbot):
    other = QWidget()
    qtbot.addWidget(other)
    other.show()
    other.activateWindow()
    qtbot.waitUntil(lambda: QApplication.activeWindow() is other, timeout=WAIT)
    return other


def became_active(qtbot, window) -> bool:
    """Activation is asynchronous offscreen: wait a little, then report."""
    try:
        qtbot.waitUntil(lambda: QApplication.activeWindow() is window, timeout=2000)
    except pytestqt.exceptions.TimeoutError:
        pass
    return QApplication.activeWindow() is window


def test_a_capture_hotkey_while_open_brings_back_the_overlay_with_the_selection(make, qtbot, clipboard):
    h = make()
    h.controller.run(Command.CAPTURE)
    main, side = h.controller.overlays
    qi.drag(side, 10, 10, 110, 60)
    steal_focus(qtbot)
    h.controller.handle_hotkey(hotkey_id(Command.OCR))
    assert became_active(qtbot, side)
    assert QApplication.focusWidget() is side
    assert h.controller.overlays == (main, side)
    assert len(h.capture.taken) == 1
    assert side.selection == Rect(815, 15, 150, 75)
    qi.key(side, Qt.Key.Key_Return)
    got = decode_png(bytes(clipboard.mimeData().data("image/png")))
    assert pixels(got) == pixels(crop(h.capture.image, Rect(815, 15, 150, 75)))


def test_without_a_selection_the_first_overlay_comes_back(make, qtbot):
    h = make()
    h.controller.run(Command.TRANSLATE)
    steal_focus(qtbot)
    h.controller.run(Command.CAPTURE)
    assert became_active(qtbot, h.controller.overlays[0])
    assert len(h.capture.taken) == 1


def test_the_menu_brings_the_overlay_back_too(make, qtbot):
    h = make()
    h.controller.run(Command.CAPTURE)
    main, side = h.controller.overlays
    qi.drag(main, 10, 10, 110, 60)
    steal_focus(qtbot)
    h.menu_action(Command.TABLE_OCR).trigger()
    assert became_active(qtbot, main)
    assert len(h.capture.taken) == 1


def test_marks_and_tool_stay_when_the_overlay_comes_back(make, qtbot):
    h = make()
    h.controller.run(Command.CAPTURE)
    main = h.controller.overlays[0]
    qi.drag(main, 10, 10, 210, 160)
    annotate_tb(main, "tool-rect").click()
    qi.drag(main, 30, 30, 90, 90)
    marks = main.marks
    steal_focus(qtbot)
    h.controller.run(Command.CAPTURE)
    assert became_active(qtbot, main)
    assert main.marks == marks and len(marks) == 1
    assert main.toolbar.tool is Tool.RECT


def test_an_open_save_dialog_comes_back_on_top(make, qtbot):
    h = make()
    overlay, dialog = save_capture(h)
    steal_focus(qtbot)
    h.controller.run(Command.CAPTURE)
    assert dialog.isVisible()
    assert became_active(qtbot, dialog)
    assert len(h.capture.taken) == 1


# --- M6 WI-4: the translation window takes typed and edited text (PRD F19-4 to F19-7) ----------
# Pinned: "翻译" / Ctrl+Enter in the window translates the source box as it is,
# with the chosen target, without a capture and without moving the window; the
# translation lands on the clipboard (failure: clipboard unchanged). A
# screenshot translation uses the chosen target too and gives the window focus.
# Typed text keeps no record, so debug mode writes nothing for it.

from snapocr.translators.errors import TranslationError, TranslationErrorKind  # noqa: E402

CTRL = Qt.KeyboardModifier.ControlModifier


def finish_screenshot_translation(h, target=None):
    popup = h.controller.popup
    h.controller.run(Command.TRANSLATE)
    h.select(100, 100, 300, 160)
    h.qtbot.waitUntil(lambda: isinstance(popup.state, Done), timeout=WAIT)
    return popup


def test_edited_source_is_translated_again_in_place(make, clipboard):
    h = make()
    popup = finish_screenshot_translation(h)
    assert clipboard.text() == f"T({EXPECTED})"
    where = popup.geometry()
    popup.source_view.setPlainText("改过的原文")
    h.qtbot.mouseClick(popup.translate_button, Qt.MouseButton.LeftButton)
    h.qtbot.waitUntil(lambda: popup.state == Done("改过的原文", "T(改过的原文)"), timeout=WAIT)
    assert clipboard.text() == "T(改过的原文)"
    assert popup.geometry() == where
    assert popup.source_view.toPlainText() == "改过的原文"
    assert len(h.capture.taken) == 1


def test_typed_text_with_a_chosen_target(make, clipboard):
    h = make()
    popup = h.controller.popup
    popup.show()
    popup.source_view.setPlainText("Hello")
    popup.target_box.setCurrentIndex(1)  # 译成中文
    h.qtbot.keyClick(popup.source_view, Qt.Key.Key_Return, CTRL)
    h.qtbot.waitUntil(lambda: popup.state == Done("Hello", "zh:T(Hello)"), timeout=WAIT)
    assert clipboard.text() == "zh:T(Hello)"
    assert popup.translation_view.toPlainText() == "zh:T(Hello)"
    assert h.capture.taken == []


def test_screenshot_translation_uses_the_chosen_target(make, clipboard):
    h = make()
    h.controller.popup.target_box.setCurrentIndex(2)  # 译成英文
    popup = finish_screenshot_translation(h)
    assert popup.state == Done(EXPECTED, f"en:T({EXPECTED})")
    assert clipboard.text() == f"en:T({EXPECTED})"


def test_typed_text_failure_keeps_the_clipboard(make, clipboard):
    err = TranslationError(TranslationErrorKind.UNREACHABLE, base_url="http://127.0.0.1:11434", model="m")
    h = make(translator=ScriptedTranslator(err))
    popup = h.controller.popup
    popup.show()
    popup.source_view.setPlainText("Hello")
    h.qtbot.mouseClick(popup.translate_button, Qt.MouseButton.LeftButton)
    h.qtbot.waitUntil(lambda: isinstance(popup.state, Failed), timeout=WAIT)
    assert clipboard.text() == SENTINEL
    assert popup.source_view.toPlainText() == "Hello"
    assert popup.translation_view.toPlainText() == popup.state.message


def test_screenshot_translation_gives_the_window_focus(make, qtbot, clipboard):
    h = make()
    popup = finish_screenshot_translation(h)
    assert became_active(qtbot, popup)


def test_debug_writes_nothing_for_typed_text(make, clipboard):
    h = make(debug=True)
    popup = h.controller.popup
    popup.show()
    popup.source_view.setPlainText("Hello")
    h.qtbot.mouseClick(popup.translate_button, Qt.MouseButton.LeftButton)
    h.qtbot.waitUntil(lambda: isinstance(popup.state, Done), timeout=WAIT)
    assert debug_files(h) == []


def test_a_request_after_quit_does_nothing(make, clipboard):
    h = make()
    h.controller.run(Command.QUIT)
    h.controller.popup.translate_requested.emit("Hello", None)  # the runner is shut down: no submit
    h.qtbot.wait(50)
    assert h.controller.popup.state is None
    assert clipboard.text() == SENTINEL

