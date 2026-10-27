"""Composition root: start-up and shutdown of the real application (F5, F9, plan D5, D12).

Order: QApplication -> single instance (before anything visible or global) ->
config -> controller with the real desktop boundaries -> tray -> hotkeys and
engine warm-up (``controller.start``). Shutdown releases everything in
reverse and renders the clipboard so a screenshot survives the exit (R7).
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QEvent, QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

from snapocr.actions.flows import FlowDeps
from snapocr.actions.outcomes import Notice
from snapocr.app import DEFAULT_LOG_DIR, install_excepthook, parse_args, setup_logging
from snapocr.autostart import autostart_command
from snapocr.commands import Command
from snapocr.config.files import instance_name, load_config_file
from snapocr.engines.holder import EngineHolder
from snapocr.engines.rapidocr_engine import RapidOcrEngine
from snapocr.gui.controller import AppController
from snapocr.gui.icons import app_icon
from snapocr.gui.platform import native_clipboard, shell
from snapocr.gui.platform.autostart import RegistryAutostart
from snapocr.gui.platform.capture import DesktopCapture
from snapocr.gui.platform.hotkeys import NativeHotkeys
from snapocr.gui.platform.single_instance import InstanceLock, acquire
from snapocr.gui.platform.tray import Tray
from snapocr.translators.openai_compat import OpenAICompatTranslator, list_models

ALREADY_RUNNING_MS = 3000


class _TrayNotifier:
    """The controller needs a notifier before the tray (which needs the controller's menu) exists."""

    def __init__(self) -> None:
        self.tray: Tray | None = None

    def notify(self, notice: Notice) -> None:
        self.tray.notify(notice)


@dataclass
class RunningApp:
    app: QApplication
    lock: InstanceLock
    controller: AppController
    tray: Tray
    hotkeys: NativeHotkeys

    closed: bool = False

    def shutdown(self) -> None:
        """F5-5; safe to call twice."""
        if self.closed:
            return
        self.closed = True
        self.controller.run(Command.QUIT)
        self.hotkeys.close()
        self.tray.hide()
        native_clipboard.flush()
        self.lock.release()
        # Free the Qt objects now, while the QApplication exists. Left to Python's
        # garbage collector they may die after it, or the tray after its menu,
        # and the process then crashes on exit (found in WI-22).
        self.tray.icon.setContextMenu(None)
        c = self.controller
        for obj in (c.popup, c.history_window, c.settings_window, c.menu, c):
            obj.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def _show_already_running() -> None:
    box = QMessageBox(QMessageBox.Icon.Information, "snapocr", "snapocr 已在运行。")
    QTimer.singleShot(ALREADY_RUNNING_MS, box.accept)
    box.exec()


def start(argv: list[str]) -> RunningApp | None:
    """Start snapocr; None when another instance already runs on the same config (F5-4)."""
    args = parse_args(argv[1:])
    app = QApplication.instance() or QApplication(argv[:1])
    app.setQuitOnLastWindowClosed(False)
    app.setWindowIcon(app_icon())

    lock = acquire(instance_name(args.config))
    if lock is None:
        _show_already_running()
        return None

    loaded = load_config_file(args.config)  # creates the template when missing (F9-1, F9-2)
    config = loaded.config
    engine = EngineHolder(lambda: RapidOcrEngine(config.ocr).load())
    deps = FlowDeps(engine, config.postprocess, config.replacements)
    hotkeys = NativeHotkeys()
    notifier = _TrayNotifier()
    controller = AppController(
        config,
        args.config,
        deps,
        make_translator=OpenAICompatTranslator,
        list_models=list_models,
        capture_provider=DesktopCapture(),
        notifier=notifier,
        hotkey_backend=hotkeys,
        autostart=RegistryAutostart(autostart_command(Path(sys.executable), args.config)),
        open_file=shell.open_file,
        quit_app=app.quit,
        startup_issues=loaded.issues,
    )
    tray = Tray(controller.menu, app_icon())
    notifier.tray = tray
    tray.show()
    hotkeys.activated.connect(controller.handle_hotkey)
    controller.start()
    return RunningApp(app, lock, controller, tray, hotkeys)


def main(argv: list[str] | None = None, *, log_dir: Path = DEFAULT_LOG_DIR) -> int:
    setup_logging(log_dir)
    install_excepthook()
    running = start(sys.argv if argv is None else argv)
    if running is None:
        return 0
    try:
        return running.app.exec()
    finally:
        running.shutdown()
