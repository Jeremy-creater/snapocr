"""WI-5: EngineHolder - lazy load, reuse, recoverable load failure (F1-5, D2)."""

from __future__ import annotations

import threading
import time

import pytest
from hypothesis import settings
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, initialize, invariant, rule

from snapocr.engines.errors import EngineLoadError, EngineRuntimeError
from snapocr.engines.holder import EngineHolder
from snapocr.engines.types import OcrResult, TextBlock

_BOX = ((0.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.0, 5.0))
_RESULT = OcrResult((TextBlock(text="hello", box=_BOX, score=0.9),))
_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16

THREADS = 8
JOIN_TIMEOUT = 10.0


class FakeEngine:
    """Stands in for a slow-to-load real engine; returns a fixed real OcrResult."""

    def __init__(self, result: OcrResult) -> None:
        self._result = result

    def recognize(self, data: bytes) -> OcrResult:
        return self._result


class ScriptedFactory:
    """Factory whose n-th call follows ``script[n]``; past the end it returns engines.

    Script items: ``"ok"`` -> new FakeEngine, or an exception instance to raise.
    """

    def __init__(self, script=(), delay: float = 0.0) -> None:
        self._script = list(script)
        self._delay = delay
        self._lock = threading.Lock()
        self.calls = 0
        self.built: list[FakeEngine] = []

    def __call__(self) -> FakeEngine:
        with self._lock:
            index = self.calls
            self.calls += 1
        if self._delay:
            time.sleep(self._delay)
        step = self._script[index] if index < len(self._script) else "ok"
        if isinstance(step, BaseException):
            raise step
        engine = FakeEngine(_RESULT)
        with self._lock:
            self.built.append(engine)
        return engine


def _load_error() -> EngineLoadError:
    return EngineLoadError(model_paths=["D:/LLM/models/det.onnx"], hint="re-download the model")


def test_get_returns_same_working_engine():
    factory = ScriptedFactory()
    holder = EngineHolder(factory)

    first = holder.get()
    second = holder.get()

    assert first is second
    assert first.recognize(_PNG) == _RESULT
    assert factory.calls == 1  # supplementary: construct-once is the specified behavior


def test_construction_is_lazy():
    original = _load_error()
    factory = ScriptedFactory([original])

    holder = EngineHolder(factory)  # must not raise: nothing is loaded yet

    assert factory.calls == 0
    with pytest.raises(EngineLoadError) as excinfo:
        holder.get()
    assert excinfo.value is original


def test_failure_then_success_recovers():
    original = _load_error()
    holder = EngineHolder(ScriptedFactory([original, "ok"]))

    with pytest.raises(EngineLoadError) as excinfo:
        holder.get()
    assert excinfo.value is original

    second = holder.get()
    assert second.recognize(_PNG) == _RESULT

    third = holder.get()
    assert third is second


def test_get_wraps_foreign_exception_with_cause():
    cause = RuntimeError("onnx exploded")
    holder = EngineHolder(ScriptedFactory([cause]))

    with pytest.raises(EngineLoadError) as excinfo:
        holder.get()

    assert excinfo.value.__cause__ is cause
    message = str(excinfo.value)
    assert "RuntimeError" in message
    assert "onnx exploded" in message


def test_get_wraps_engine_runtime_error_from_factory():
    cause = EngineRuntimeError("x")
    holder = EngineHolder(ScriptedFactory([cause]))

    with pytest.raises(EngineLoadError) as excinfo:
        holder.get()

    assert type(excinfo.value) is EngineLoadError
    assert excinfo.value.__cause__ is cause


def test_keyboard_interrupt_not_swallowed():
    interrupt = KeyboardInterrupt()
    holder = EngineHolder(ScriptedFactory([interrupt, "ok"]))

    with pytest.raises(KeyboardInterrupt) as excinfo:
        holder.get()
    assert excinfo.value is interrupt

    engine = holder.get()
    assert engine.recognize(_PNG) == _RESULT


_OUTCOMES = st.sampled_from(["ok", "load_error", "runtime_error"])


class HolderMachine(RuleBasedStateMachine):
    """Model: before the first ok every get() calls the factory and raises EngineLoadError;
    after it, get() is idempotent and the factory is never called again."""

    @initialize()
    def setup(self):
        self.next_outcome = "ok"
        self.calls = 0
        self.successes = 0
        self.loaded = None
        self.holder = EngineHolder(self._factory)

    def _factory(self):
        self.calls += 1
        if self.next_outcome == "load_error":
            raise _load_error()
        if self.next_outcome == "runtime_error":
            raise RuntimeError("boom")
        self.successes += 1
        return FakeEngine(_RESULT)

    @rule(outcome=_OUTCOMES)
    def get(self, outcome):
        self.next_outcome = outcome
        calls_before = self.calls
        if self.loaded is None:
            if outcome == "ok":
                engine = self.holder.get()
                assert engine.recognize(_PNG) == _RESULT
                self.loaded = engine
            else:
                with pytest.raises(EngineLoadError):
                    self.holder.get()
            assert self.calls == calls_before + 1
        else:
            assert self.holder.get() is self.loaded
            assert self.calls == calls_before

    @invariant()
    def constructed_at_most_once(self):
        assert self.successes <= 1
        assert (self.loaded is None) == (self.successes == 0)


HolderMachine.TestCase.settings = settings(max_examples=60, stateful_step_count=15, deadline=None)
test_holder_state_machine = HolderMachine.TestCase


def _run_concurrently(holder: EngineHolder) -> list[object]:
    barrier = threading.Barrier(THREADS, timeout=JOIN_TIMEOUT)
    results: list[object] = [None] * THREADS

    def worker(i: int) -> None:
        barrier.wait()
        try:
            results[i] = holder.get()
        except EngineLoadError as exc:
            results[i] = exc
        except BaseException as exc:  # recorded so the main thread can fail with it
            results[i] = ("unexpected", exc)

    threads = [threading.Thread(target=worker, args=(i,), daemon=True) for i in range(THREADS)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(JOIN_TIMEOUT)
    assert not any(t.is_alive() for t in threads), "worker threads did not finish in time"
    return results


def test_concurrent_first_get_constructs_once():
    factory = ScriptedFactory(delay=0.05)
    holder = EngineHolder(factory)

    results = _run_concurrently(holder)

    assert all(isinstance(r, FakeEngine) for r in results), results
    assert len({id(r) for r in results}) == 1
    assert results[0].recognize(_PNG) == _RESULT
    assert factory.calls == 1
    assert len(factory.built) == 1


def test_concurrent_first_get_with_initial_failure():
    factory = ScriptedFactory([_load_error()], delay=0.05)
    holder = EngineHolder(factory)

    results = _run_concurrently(holder)

    engines = [r for r in results if isinstance(r, FakeEngine)]
    errors = [r for r in results if isinstance(r, EngineLoadError)]
    assert len(engines) + len(errors) == THREADS, results
    assert len(engines) >= 1
    assert len({id(e) for e in engines}) == 1
    assert len(factory.built) == 1
    assert holder.get() is engines[0]
