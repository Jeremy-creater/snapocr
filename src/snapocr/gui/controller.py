"""Application controller: commands, capture sessions, jobs and what they show (F5, F7, F8, F9-3, F10).

Everything here runs on the GUI thread. OCR and translation run as jobs on
the ``JobRunner`` worker; their events come back through ``EventBridge``.
Desktop access (capture, notices, hotkeys, opening files, quitting) goes
through the injected boundary objects, so this class is tested offscreen
with fakes. Business rules live in ``snapocr.actions``; this module only
routes their results to the clipboard, the notices and the windows.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path

from PySide6.QtCore import QObject, QTimer

from snapocr.actions import messages
from snapocr.actions.flows import FlowDeps, capture_flow
from snapocr.actions.history import ResultHistory
from snapocr.actions.outcomes import Failed, Outcome, Translating
from snapocr.actions.runner import (
    JobCrashed,
    JobRunner,
    OcrDone,
    TranslateDone,
    TranslateStarted,
    ocr_job,
    translate_job,
)
from snapocr.commands import Command
from snapocr.config.files import load_config_file
from snapocr.config.schema import AppConfig, ConfigIssue
from snapocr.geometry import Rect, crop_box, logical_rect, screen_containing
from snapocr.gui import clipboard
from snapocr.gui.boundaries import Capture, CaptureError, CaptureProvider, HotkeyBackend, Notifier
from snapocr.gui.bridge import EventBridge
from snapocr.gui.history_window import LastResultWindow
from snapocr.gui.imageops import crop, encode_png
from snapocr.gui.overlay import OverlaySession, SelectionOverlay
from snapocr.gui.popup import TranslationPopup
from snapocr.gui.tray_menu import build_tray_menu
from snapocr.hotkeys import RegistrationReport, register_all, unregister_all
from snapocr.translators.types import Translator

_CAPTURE_COMMANDS = (Command.CAPTURE, Command.OCR, Command.TRANSLATE)


class AppController(QObject):
    def __init__(
        self,
        config: AppConfig,
        config_path: Path,
        flow_deps: FlowDeps,
        translator: Translator,
        *,
        capture_provider: CaptureProvider,
        notifier: Notifier,
        hotkey_backend: HotkeyBackend,
        open_file: Callable[[Path], None],
        quit_app: Callable[[], None],
        startup_issues: Sequence[ConfigIssue] = (),
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._config = config
        self._config_path = config_path
        self._deps = flow_deps
        self._translator = translator
        self._capture_provider = capture_provider
        self._notifier = notifier
        self._hotkeys = hotkey_backend
        self._open_file = open_file
        self._quit_app = quit_app
        self._startup_issues = list(startup_issues)
        self._report = RegistrationReport()
        self._session: OverlaySession | None = None
        self._overlays: tuple[SelectionOverlay, ...] = ()
        self._anchors: dict[int, tuple[Rect, Rect]] = {}  # translate job -> (anchor, available), logical
        self._quitting = False

        self.history = ResultHistory()
        self.bridge = EventBridge(self)
        self.bridge.event.connect(self._on_event)
        self.runner = JobRunner(self.bridge.post, self.history)
        self.popup = TranslationPopup()
        self.history_window = LastResultWindow(self.history)
        self.menu = build_tray_menu(config.hotkeys, self._on_menu)

    def registered_commands(self) -> tuple[Command, ...]:
        """The commands whose hotkeys were registered by ``start()`` (in hotkey-id order)."""
        return tuple(self._report.registered[i] for i in sorted(self._report.registered))

    @property
    def overlays(self) -> tuple[SelectionOverlay, ...]:
        """The overlays of the open capture session; empty when none is open."""
        return self._overlays

    # --- commands ------------------------------------------------------------

    def start(self) -> None:
        """Register hotkeys, report start-up problems (F9-3, F5-3), warm up the engine (D2)."""
        self._report = register_all(self._config.hotkeys, self._hotkeys.register)
        if self._startup_issues:
            self._notifier.notify(messages.config_issues_notice(self._startup_issues))
        if self._report.failed:
            self._notifier.notify(messages.hotkey_failed_notice(self._report.failed))
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
        elif command is Command.LAST_RESULT:
            self.history_window.show_latest()
        elif command is Command.OPEN_CONFIG:
            self._open_config()
        else:
            self._quit()

    # --- capture sessions ----------------------------------------------------------

    def _begin_capture(self, command: Command) -> None:
        if self._session is not None:
            return
        try:
            cap = self._capture_provider.capture()
        except CaptureError as err:
            self._notifier.notify(messages.capture_failed_notice(str(err)))
            return
        overlays = tuple(SelectionOverlay(crop(cap.image, crop_box(s.physical, cap.origin)), s) for s in cap.screens)
        session = OverlaySession(list(overlays), self)
        session.result.connect(lambda rect: self._on_selection(command, cap, rect))
        self._session, self._overlays = session, overlays
        session.start()

    def _end_session(self) -> None:
        for overlay in self._overlays:
            overlay.abandon()
            overlay.close()
            overlay.deleteLater()
        if self._session is not None:
            self._session.deleteLater()
        self._session, self._overlays = None, ()

    def _on_selection(self, command: Command, cap: Capture, rect: Rect | None) -> None:
        self._end_session()
        if rect is None:  # F6-3: cancelled, nothing changes
            return
        png = encode_png(crop(cap.image, crop_box(rect, cap.origin)))
        if command is Command.CAPTURE:
            self._land(capture_flow(png))
        elif command is Command.OCR:
            self.runner.submit(ocr_job(png, self._deps))
        else:
            job_id = self.runner.submit(translate_job(png, self._deps, self._translator))
            screen = screen_containing(rect, cap.screens)
            available = cap.work_areas.get(screen.name, screen.logical)
            self._anchors[job_id] = (logical_rect(screen, rect), available)

    # --- job events (GUI thread) --------------------------------------------------------

    def _land(self, outcome: Outcome) -> None:
        clipboard.apply(outcome.clipboard)
        if outcome.notice is not None:
            self._notifier.notify(outcome.notice)

    def _on_event(self, event: object) -> None:
        if isinstance(event, OcrDone):
            self._anchors.pop(event.job_id, None)
            self._land(event.outcome)
            self.history_window.on_new_result()
        elif isinstance(event, TranslateStarted):
            # One FIFO worker: this is always the newest translate job. Its anchor is
            # set in _on_selection, which returns before any queued event is handled.
            self.popup.apply(event.job_id, Translating(event.stage.text))
            self.popup.place(*self._anchors[event.job_id])
        elif isinstance(event, TranslateDone):
            self._anchors.pop(event.job_id, None)
            self.popup.apply(event.job_id, event.outcome.popup)
            clipboard.apply(event.outcome.clipboard)
            self.history_window.on_new_result()
        elif isinstance(event, JobCrashed):
            self._anchors.pop(event.job_id, None)
            self._notifier.notify(messages.job_crashed_notice(event.exc_type_name))
            state = self.popup.state
            if self.popup.job_id == event.job_id and isinstance(state, Translating):
                self.popup.apply(event.job_id, Failed(state.source, messages.job_crashed_text(event.exc_type_name)))
        # WarmedUp: nothing to show (plan A10)

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
        self.popup.hide()
        self.history_window.hide()
        self._quit_app()
