"""Composition root: start-up and shutdown of the real application (F5, F9, plan D5, D12).

Order: QApplication -> single instance (before anything visible or global) ->
config -> controller with the real desktop boundaries -> tray -> hotkeys and
engine warm-up (``controller.start``). Shutdown releases everything in
reverse and renders the clipboard so a screenshot survives the exit (R7).
"""

from __future__ import annotations

import importlib
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

from PySide6.QtCore import QCoreApplication, QEvent, QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

from snapocr.actions.flows import FlowDeps
from snapocr.actions.outcomes import Notice
from snapocr.app import DEFAULT_LOG_DIR, install_excepthook, kit_module, parse_args, runtime_issues, setup_logging
from snapocr.commands import Command
from snapocr.config.files import load_config_file
from snapocr.engines.holder import EngineHolder
from snapocr.engines.rapidocr_engine import RapidOcrEngine
from snapocr.gui.controller import AppController
from snapocr.gui.icons import app_icon
from snapocr.gui.platform.tray import Tray
from snapocr.translators.openai_compat import OpenAICompatTranslator, list_models

ALREADY_RUNNING_MS = 3000


def platform_kit() -> ModuleType:
    """``snapocr.gui.platform.win`` or ``.mac.kit``: the same names on both (M9 plan D12)."""
    return importlib.import_module(kit_module(sys.platform))


class _TrayNotifier:
    """The controller needs a notifier before the tray (which needs the controller's menu) exists."""

    def __init__(self) -> None:
        self.tray: Tray | None = None

    def notify(self, notice: Notice) -> None:
        self.tray.notify(notice)


@dataclass
class RunningApp:
    app: QApplication
    lock: Any  # the kit's InstanceLock
    controller: AppController
    tray: Tray
    hotkeys: Any  # the kit's Hotkeys
    kit: ModuleType

    closed: bool = False

    def shutdown(self) -> None:
        """F5-5; safe to call twice."""
        if self.closed:
            return
        self.closed = True
        self.controller.run(Command.QUIT)
        self.hotkeys.close()
        self.tray.hide()
        self.kit.flush_clipboard()
        self.lock.release()
        # Free the Qt objects now, while the QApplication exists. Left to Python's
        # garbage collector they may die after it, or the tray after its menu,
        # and the process then crashes on exit (found in WI-22).
        self.tray.icon.setContextMenu(None)
        c = self.controller
        for obj in (c.popup, c.settings_window, c.menu, c):
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
    kit = platform_kit()
    kit.prepare_app(app)  # Mac: no Dock icon (D17), before anything is shown

    lock = kit.acquire(args.config)
    if lock is None:
        _show_already_running()
        return None

    loaded = load_config_file(args.config)  # creates the template when missing (F9-1, F9-2)
    config = loaded.config
    engine = EngineHolder(lambda: RapidOcrEngine(config.ocr).load())
    deps = FlowDeps(engine, config.postprocess, config.replacements)
    hotkeys = kit.Hotkeys()
    notifier = _TrayNotifier()
    controller = AppController(
        config,
        args.config,
        deps,
        make_translator=OpenAICompatTranslator,
        list_models=list_models,
        capture_provider=kit.Capture(),
        notifier=notifier,
        hotkey_backend=hotkeys,
        autostart=kit.make_autostart(Path(sys.executable), args.config, getattr(sys, "frozen", False)),  # F22-2
        open_file=kit.open_file,
        quit_app=app.quit,
        startup_issues=loaded.issues + runtime_issues(),  # F9-3, F21-2
        glass=kit.glass(),
        prepare_overlay=kit.prepare_overlay,  # Mac: above the menu bar and Dock (F23-4)
    )
    tray = Tray(controller.menu, app_icon())
    notifier.tray = tray
    tray.show()
    hotkeys.activated.connect(controller.handle_hotkey)
    controller.start()
    return RunningApp(app, lock, controller, tray, hotkeys, kit)


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
