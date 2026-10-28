"""Application controller: commands, capture sessions, jobs and what they show (F5, F7, F8, F9-3, F11, F19).

The capture action's overlays are in annotation mode (F14); the last style
picked there is remembered for the next capture, in memory only (M4 plan D13).

Everything here runs on the GUI thread. OCR and translation run as jobs on
the ``JobRunner`` worker; their events come back through ``EventBridge``.
Desktop access (capture, notices, hotkeys, start at login, opening files,
quitting) goes
through the injected boundary objects, so this class is tested offscreen
with fakes. Business rules live in ``snapocr.actions``; this module only
routes their results to the clipboard, the notices and the windows.
"""

from __future__ import annotations

import dataclasses
import datetime
import threading
from collections.abc import Callable, Sequence
from pathlib import Path

from PySide6.QtCore import QObject, QTimer
from PySide6.QtGui import QCursor, QGuiApplication, QImage

from snapocr.actions import messages
from snapocr.actions.debug import DEBUG_DIR, DebugDump
from snapocr.actions.flows import FlowDeps, capture_flow
from snapocr.actions.outcomes import Failed, Outcome, Translating
from snapocr.actions.saving import save_flow, suggest_path
from snapocr.actions.runner import (
    JobCrashed,
    JobRunner,
    OcrDone,
    TranslateDone,
    TranslateStarted,
    code_ocr_job,
    ocr_job,
    table_ocr_job,
    text_translate_job,
    translate_job,
)
from snapocr.annotate import DEFAULT_STYLE, Style
from snapocr.commands import Command
from snapocr.config.files import load_config_file
from snapocr.config.schema import AppConfig, ConfigIssue
from snapocr.config.settings import Settings, apply, changes, check, settings_of
from snapocr.config.writer import ConfigWriteError, write_changes
from snapocr.geometry import Rect, center_in, crop_box, logical_rect, screen_containing
from snapocr.gui import clipboard
from snapocr.gui.boundaries import Autostart, Capture, CaptureError, CaptureProvider, HotkeyBackend, Notifier
from snapocr.gui.bridge import EventBridge
from snapocr.gui.imageops import crop, encode_png
from snapocr.gui.marks_paint import render_marked
from snapocr.gui.overlay import OverlaySession, SelectionOverlay
from snapocr.gui.pin_window import PinWindow
from snapocr.gui.popup import TranslationPopup
from snapocr.gui.settings_window import SettingsWindow
from snapocr.gui.tray_menu import build_tray_menu, update_tray_menu
from snapocr.hotkeys import RegistrationReport, register_all, unregister_all
from snapocr.translators.config import TranslatorConfig
from snapocr.translators.errors import TranslationError
from snapocr.translators.types import Translator

_CAPTURE_COMMANDS = (Command.CAPTURE, Command.OCR, Command.TRANSLATE, Command.CODE_OCR, Command.TABLE_OCR)


@dataclasses.dataclass(frozen=True)
class _ModelsListed:
    """The model list for one opening of the settings window (F11-7)."""

    request: int
    models: tuple[str, ...]
    hint: str | None


class AppController(QObject):
    def __init__(
        self,
        config: AppConfig,
        config_path: Path,
        flow_deps: FlowDeps,
        *,
        make_translator: Callable[[TranslatorConfig], Translator],
        list_models: Callable[[TranslatorConfig], Sequence[str]],
        capture_provider: CaptureProvider,
        notifier: Notifier,
        hotkey_backend: HotkeyBackend,
        autostart: Autostart,
        open_file: Callable[[Path], None],
        quit_app: Callable[[], None],
        startup_issues: Sequence[ConfigIssue] = (),
        debug_dir: Path = DEBUG_DIR,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._config = config
        self._config_path = config_path
        self._deps = dataclasses.replace(flow_deps, show_text=config.show_text)  # F7-2: the config decides
        self._make_translator = make_translator
        self._translator = make_translator(config.translator)
        self._list_models = list_models
        self._models_request = 0  # numbers the settings openings; stale model lists are dropped
        self._capture_provider = capture_provider
        self._notifier = notifier
        self._hotkeys = hotkey_backend
        self._autostart = autostart
        self._open_file = open_file
        self._quit_app = quit_app
        self._startup_issues = list(startup_issues)
        self._report = RegistrationReport()
        self._session: OverlaySession | None = None
        self._overlays: tuple[SelectionOverlay, ...] = ()
        self._style: Style = DEFAULT_STYLE  # annotation colour and size (F14-4)
        self._pins: list[PinWindow] = []  # F15-3: memory only
        self._anchors: dict[int, tuple[Rect, Rect]] = {}  # translate job -> (anchor, available), logical
        self._last_translate_job = -1  # the newest translate job submitted
        self._dropped_through = -1  # F19-3 (v1.5): translate jobs up to this id were cleared by Alt+4
        self._quitting = False
        self._paused = False  # hotkeys released while the settings window is open (plan D5)

        self.bridge = EventBridge(self)
        self.bridge.event.connect(self._on_event)
        self._debug_dir = debug_dir
        on_record = DebugDump(debug_dir) if config.debug else None  # F12: read once at start
        self.runner = JobRunner(self.bridge.post, on_record)
        self.popup = TranslationPopup()
        self.popup.translate_requested.connect(self._translate_text)
        self.menu = build_tray_menu(config.hotkeys, self._on_menu)
        self.settings_window = SettingsWindow()
        self.settings_window.save_requested.connect(self._save_settings)
        self.settings_window.advanced_requested.connect(lambda: self.run(Command.OPEN_CONFIG))
        self.settings_window.closed.connect(self._settings_closed)

    def registered_commands(self) -> tuple[Command, ...]:
        """The commands whose hotkeys were registered by ``start()`` (in hotkey-id order)."""
        return tuple(self._report.registered[i] for i in sorted(self._report.registered))

    @property
    def pins(self) -> tuple[PinWindow, ...]:
        """The open pinned screenshots (F15), oldest first."""
        return tuple(self._pins)

    @property
    def overlays(self) -> tuple[SelectionOverlay, ...]:
        """The overlays of the open capture session; empty when none is open."""
        return self._overlays

    # --- commands ------------------------------------------------------------

    def start(self) -> None:
        """Register hotkeys, report start-up problems (F9-3, F5-3) and debug mode (F12-2), warm up (D2)."""
        self._report = register_all(self._config.hotkeys, self._hotkeys.register)
        if self._startup_issues:
            self._notifier.notify(messages.config_issues_notice(self._startup_issues))
        if self._report.failed:
            self._notifier.notify(messages.hotkey_failed_notice(self._report.failed))
        if self._config.debug:
            self._notifier.notify(messages.debug_on_notice(self._debug_dir))
        self.runner.submit_warmup(self._deps.engine)

    def handle_hotkey(self, hotkey_id: int) -> None:
        command = self._report.registered.get(hotkey_id)
        if command is not None:
            self.run(command)

    def _on_menu(self, command: Command) -> None:
        if command in _CAPTURE_COMMANDS:
            # Let the menu finish closing before the screen is captured.
            QTimer.singleShot(0, lambda: self.run(command))
        else:
            self.run(command)

    def run(self, command: Command) -> None:
        if self._quitting:
            return
        if command in _CAPTURE_COMMANDS:
            self._begin_capture(command)
        elif command is Command.TRANSLATE_TEXT:
            self._open_translation_window()
        elif command is Command.SETTINGS:
            self._open_settings()
        elif command is Command.OPEN_CONFIG:
            self._open_config()
        else:
            self._quit()

    # --- capture sessions ----------------------------------------------------------

    def _begin_capture(self, command: Command) -> None:
        if self._session is not None:  # F18-2: no second capture; the open one comes back
            self._session.refocus()
            return
        try:
            cap = self._capture_provider.capture()
        except CaptureError as err:
            self._notifier.notify(messages.capture_failed_notice(str(err)))
            return
        annotate = command is Command.CAPTURE
        overlays = tuple(
            SelectionOverlay(
                crop(cap.image, crop_box(s.physical, cap.origin)),
                s,
                annotate=annotate,
                style=self._style,
                save_target=self._save_target,
            )
            for s in cap.screens
        )
        for overlay in overlays:
            overlay.style_changed.connect(self._remember_style)
        session = OverlaySession(list(overlays), self)
        session.result.connect(lambda rect: self._on_selection(command, cap, rect))
        self._session, self._overlays = session, overlays
        session.start()

    def _save_target(self) -> Path:
        """F17-2, F17-3: where the save-as dialog starts."""
        return suggest_path(self._config.save_dir, datetime.datetime.now())

    def _remember_style(self, style: Style) -> None:
        self._style = style

    def _end_session(self) -> None:
        for overlay in self._overlays:
            overlay.abandon()
            overlay.close()
            overlay.deleteLater()
        if self._session is not None:
            self._session.deleteLater()
        self._session, self._overlays = None, ()

    def _on_selection(self, command: Command, cap: Capture, rect: Rect | None) -> None:
        session = self._session  # only capture overlays annotate, pin or save
        marks, action, save_path = session.marks, session.action, session.save_path
        self._end_session()
        if rect is None:  # F6-3: cancelled, nothing changes
            return
        image = crop(cap.image, crop_box(rect, cap.origin))
        if marks:
            image = render_marked(image, marks, (rect.x, rect.y))
        if action == "pin":  # F15-1: no clipboard change, no notice
            self._pin(image, logical_rect(screen_containing(rect, cap.screens), rect))
            return
        png = encode_png(image)
        if action == "save":  # F17-1: the picked file, and onto the clipboard
            self._land(save_flow(png, save_path))
        elif command is Command.CAPTURE:
            self._land(capture_flow(png))
        elif command is Command.OCR:
            self.runner.submit(ocr_job(png, self._deps))
        elif command is Command.CODE_OCR:
            self.runner.submit(code_ocr_job(png, self._deps))
        elif command is Command.TABLE_OCR:
            self.runner.submit(table_ocr_job(png, self._deps))
        else:
            job_id = self._last_translate_job = self.runner.submit(
                translate_job(png, self._deps, self._translator, self.popup.target)
            )
            screen = screen_containing(rect, cap.screens)
            available = cap.work_areas.get(screen.name, screen.logical)
            self._anchors[job_id] = (logical_rect(screen, rect), available)

    def _open_translation_window(self) -> None:
        """F19-3: blank, centred on the screen under the mouse when hidden; focus in the source.

        Every translation submitted so far is dropped (v1.5): no window, no clipboard.
        """
        self._dropped_through = self._last_translate_job
        popup = self.popup
        popup.clear()
        if not popup.isVisible():
            screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
            g = screen.availableGeometry()
            r = center_in((popup.width(), popup.height()), Rect(g.x(), g.y(), g.width(), g.height()))
            popup.setGeometry(r.x, r.y, r.w, r.h)
            popup.show()
        popup.raise_()
        popup.activateWindow()
        popup.focus_source()

    def _translate_text(self, text: str, target: str | None) -> None:
        """F19-5: the window's source box, translated where the window is (no anchor)."""
        if not self._quitting:
            self._last_translate_job = self.runner.submit(text_translate_job(text, self._translator, target))

    def _pin(self, image: QImage, geometry: Rect) -> None:
        window = PinWindow(image, geometry)
        window.closed.connect(lambda: self._unpin(window))
        self._pins.append(window)
        window.show()
        window.raise_()
        window.activateWindow()

    def _unpin(self, window: PinWindow) -> None:
        self._pins.remove(window)  # a window sends ``closed`` once
        window.deleteLater()

    # --- job events (GUI thread) --------------------------------------------------------

    def _land(self, outcome: Outcome) -> None:
        clipboard.apply(outcome.clipboard)
        if outcome.notice is not None:
            self._notifier.notify(outcome.notice)

    def _on_event(self, event: object) -> None:
        if isinstance(event, OcrDone):
            self._anchors.pop(event.job_id, None)
            self._land(event.outcome)
        elif isinstance(event, (TranslateStarted, TranslateDone)) and event.job_id <= self._dropped_through:
            self._anchors.pop(event.job_id, None)  # cleared by Alt+4 (F19-3 v1.5)
        elif isinstance(event, TranslateStarted):
            # Recognition runs FIFO on one worker (F18-1 moves only the model request
            # off it): this is always the newest translate job. A screenshot job's anchor
            # is set in _on_selection, which returns before any queued event is handled;
            # typed text (F19-5) has none.
            self.popup.apply(event.job_id, Translating(event.stage.text))
            anchor = self._anchors.get(event.job_id)
            if anchor is not None:  # a screenshot translation: next to the selection, with focus (F19-4)
                self.popup.place(*anchor)
                self.popup.activateWindow()
                self.popup.source_view.setFocus()
        elif isinstance(event, TranslateDone):
            self._anchors.pop(event.job_id, None)
            self.popup.apply(event.job_id, event.outcome.popup)
            clipboard.apply(event.outcome.clipboard)
        elif isinstance(event, JobCrashed):
            self._anchors.pop(event.job_id, None)
            self._notifier.notify(messages.job_crashed_notice(event.exc_type_name))
            state = self.popup.state
            if self.popup.job_id == event.job_id and isinstance(state, Translating):
                self.popup.apply(event.job_id, Failed(state.source, messages.job_crashed_text(event.exc_type_name)))
        elif isinstance(event, _ModelsListed):
            # Only the answer to the latest opening, and only while the window is open.
            if event.request == self._models_request and self.settings_window.isVisible():
                self.settings_window.set_models(event.models, event.hint)
        # WarmedUp: nothing to show (plan A10)

    # --- settings window (F11) ------------------------------------------------------------

    def _autostart_enabled(self) -> bool:
        try:
            return self._autostart.is_enabled()
        except OSError:
            return False

    def _request_models(self) -> None:
        """F11-7, plan D12: read the model list off the GUI thread (a refused connection takes ~2 s)."""
        self._models_request += 1
        self.settings_window.set_models((), messages.MODELS_LOADING)
        threading.Thread(
            target=self._fetch_models,
            args=(self._models_request, self._config.translator),
            name="snapocr-models",
            daemon=True,
        ).start()

    def _fetch_models(self, request: int, config: TranslatorConfig) -> None:
        """Worker thread: list the models and post the result to the GUI thread."""
        try:
            listed = _ModelsListed(request, tuple(self._list_models(config)), None)
        except TranslationError as err:
            listed = _ModelsListed(request, (), messages.models_problem_text(err))
        try:
            self.bridge.post(listed)
        except RuntimeError:  # the controller was deleted while the service answered (shutdown)
            pass

    def _open_settings(self) -> None:
        window = self.settings_window
        if not window.isVisible():
            # Plan D5: a registered combination reaches us as WM_HOTKEY, never as a key press.
            unregister_all(self._report, self._hotkeys.unregister)
            self._report = RegistrationReport()
            self._paused = True
            window.load(settings_of(self._config), self._autostart_enabled())
            self._request_models()
            window.show()
        window.raise_()
        window.activateWindow()

    def _save_settings(self, new: Settings, autostart: bool) -> None:
        """Plan D11: check, try the hotkeys, start at login, file; then apply. Any failure undoes the rest."""
        window = self.settings_window
        problems = check(new)
        if problems:
            window.show_problems([messages.settings_problem_text(p) for p in problems])
            return
        trial = register_all(new.hotkeys, self._hotkeys.register)
        if trial.failed:
            unregister_all(trial, self._hotkeys.unregister)
            window.show_problems([messages.hotkey_failure_line(f) for f in trial.failed])
            return
        was_on = self._autostart_enabled()
        try:
            if autostart != was_on:
                self._autostart.set_enabled(autostart)
        except OSError as err:
            unregister_all(trial, self._hotkeys.unregister)
            window.show_problems([messages.autostart_failed_text(err)])
            return
        delta = changes(settings_of(self._config), new)
        try:
            if delta:
                write_changes(self._config_path, delta)
        except ConfigWriteError as err:
            unregister_all(trial, self._hotkeys.unregister)
            if autostart != was_on:
                try:
                    self._autostart.set_enabled(was_on)
                except OSError:
                    pass  # the window reports the file problem; start at login stays as chosen
            window.show_problems([str(err)])
            return
        self._config = apply(self._config, new)
        self._deps = dataclasses.replace(self._deps, options=self._config.postprocess, show_text=self._config.show_text)
        self._translator = self._make_translator(self._config.translator)
        self._report = trial
        self._paused = False
        update_tray_menu(self.menu, self._config.hotkeys)
        self._notifier.notify(messages.settings_saved_notice())
        window.finish()

    def _settings_closed(self) -> None:
        """Closed without saving: the hotkeys from before come back (F5-3 if one cannot)."""
        if not self._paused or self._quitting:
            return
        self._paused = False
        self._report = register_all(self._config.hotkeys, self._hotkeys.register)
        if self._report.failed:
            self._notifier.notify(messages.hotkey_failed_notice(self._report.failed))

    # --- config and quit ----------------------------------------------------------------

    def _open_config(self) -> None:
        path = self._config_path
        if not path.exists():
            result = load_config_file(path)  # creates the template, never overwrites
            if not result.created:
                self._notifier.notify(messages.config_issues_notice(result.issues))
                return
        try:
            self._open_file(path)
        except OSError as err:
            self._notifier.notify(messages.open_config_failed_notice(path, err.strerror or str(err)))
            return
        self._notifier.notify(messages.config_opened_notice())

    def _quit(self) -> None:
        """F5-5: release hotkeys, stop the worker, close windows, then leave the event loop."""
        self._quitting = True
        unregister_all(self._report, self._hotkeys.unregister)
        self.runner.shutdown()
        self._end_session()
        for pin in tuple(self._pins):
            pin.close()
        self.popup.hide()
        self.settings_window.hide()
        self._quit_app()
