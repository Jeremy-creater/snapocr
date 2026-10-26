"""Runner events -> Qt signal on the GUI thread (plan D2).

``EventBridge.post`` is the ``on_event`` callback of ``JobRunner``. It is
called on the worker thread; the bridge lives on the GUI thread, so Qt queues
the signal and its slots run there.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal


class EventBridge(QObject):
    event = Signal(object)

    def post(self, event: object) -> None:
        """Safe to call from any thread."""
        self.event.emit(event)
