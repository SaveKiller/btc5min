"""Wrapper Cursor SDK: patch Windows + call_model one-shot (pattern aitube / docs/cursor-SDK.md)."""

from __future__ import annotations

import codecs
import os
import sys
import time
from collections.abc import Callable
from typing import Any, Mapping

ProgressCb = Callable[[str, str], None]


def _patch_cursor_sdk_windows() -> None:
    """cursor-sdk usa select() su pipe stderr: su Windows fallisce con WinError 10038."""
    if sys.platform != "win32":
        return
    import cursor_sdk._bridge as bridge

    def _read_discovery(process, timeout: float) -> Mapping[str, Any]:
        if process.stderr is None:
            raise bridge.CursorSDKError("Bridge process stderr is unavailable")
        stderr_fd = process.stderr.fileno()
        was_blocking = os.get_blocking(stderr_fd)
        os.set_blocking(stderr_fd, False)
        try:
            decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
            deadline = time.monotonic() + timeout
            stderr_lines: list[str] = []
            pending = ""

            def drain_available() -> Mapping[str, Any] | None:
                nonlocal pending
                while True:
                    try:
                        chunk = os.read(stderr_fd, 8192)
                    except BlockingIOError:
                        return None
                    if not chunk:
                        final_text = decoder.decode(b"", final=True)
                        if final_text:
                            pending += final_text
                        if pending:
                            line, pending = pending, ""
                            stderr_lines.append(line)
                            return bridge.parse_discovery_line(line)
                        return None
                    pending += decoder.decode(chunk)
                    while "\n" in pending:
                        line, pending = pending.split("\n", 1)
                        line += "\n"
                        stderr_lines.append(line)
                        discovery = bridge.parse_discovery_line(line)
                        if discovery is not None:
                            return discovery

            while time.monotonic() < deadline:
                discovery = drain_available()
                if discovery is not None:
                    return discovery
                if process.poll() is not None:
                    discovery = drain_available()
                    if discovery is not None:
                        return discovery
                    raise bridge.CursorSDKError(
                        f"Bridge exited before discovery with status {process.poll()}: "
                        + "".join(stderr_lines) + pending
                    )
                time.sleep(0.05)
            raise bridge.CursorSDKError("Timed out waiting for bridge discovery")
        finally:
            os.set_blocking(stderr_fd, was_blocking)

    bridge._read_discovery = _read_discovery


_patch_cursor_sdk_windows()

from cursor_sdk import (  # noqa: E402
    Agent, CursorAgentError, LocalAgentOptions, ModelParameterValue, ModelSelection,
)

_RETRIES = 3
_RETRY_DELAY_SEC = 15

_META_MARKERS = (
    "ho salvato", "file salvato", "salvato in `", "I saved", "I've created",
    "created the file", "wrote the file",
)


def _emit(on_progress: ProgressCb | None, phase: str, message: str) -> None:
    if on_progress is not None:
        on_progress(phase, message)


def call_model(
    prompt: str, *, model_id: str, params: dict[str, str], cwd: str,
    reject_meta: bool = True, model_label: str | None = None,
    on_progress: ProgressCb | None = None, task_label: str = "model",
) -> str:
    """Invoca Cursor Agent locale; restituisce solo il testo del risultato."""
    api_key = os.environ["CURSOR_API_KEY"]
    label = model_label or model_id
    model = ModelSelection(
        id=model_id,
        params=[ModelParameterValue(id=k, value=v) for k, v in params.items()],
    )
    last_err: Exception | None = None
    for attempt in range(1, _RETRIES + 1):
        if attempt > 1:
            _emit(
                on_progress, "cursor_retry",
                f"Errore Cursor sulla run precedente — ritento {task_label} "
                f"({attempt}/{_RETRIES}) tra {_RETRY_DELAY_SEC}s…",
            )
            time.sleep(_RETRY_DELAY_SEC)
        _emit(
            on_progress, "cursor_start",
            f"Avvio agente Cursor per {task_label} con {label}"
            + (f" (tentativo {attempt}/{_RETRIES})" if attempt > 1 else "") + "…",
        )
        try:
            with Agent.create(
                api_key=api_key,
                model=model,
                local=LocalAgentOptions(cwd=cwd, auto_review=False),
            ) as agent:
                _emit(
                    on_progress, "cursor_send",
                    f"Prompt inviato a {label} — attesa risposta ({task_label})…",
                )
                run = agent.send(prompt)
                t0 = time.monotonic()
                result = run.wait()
        except CursorAgentError as e:
            raise RuntimeError(f"Cursor startup failed: {e.message}") from e
        if result.status == "finished" and result.result and result.result.strip():
            text = result.result.strip()
            elapsed = int(time.monotonic() - t0)
            _emit(
                on_progress, "cursor_done",
                f"Risposta ricevuta da {label} ({task_label}) in {elapsed}s "
                f"({len(text)} caratteri)…",
            )
            if reject_meta:
                for marker in _META_MARKERS:
                    if marker.lower() in text.lower():
                        raise RuntimeError(f"Cursor meta-commentary instead of code (found {marker!r})")
            return text
        last_err = RuntimeError(
            f"Cursor run failed: status={result.status} run_id={result.id} attempt={attempt}")
        print(f"cursor_client: {last_err}", flush=True)
        _emit(
            on_progress, "cursor_fail",
            f"Run Cursor fallita (status={result.status}) per {task_label}"
            + (f" — ritento…" if attempt < _RETRIES else " — tentativi esauriti"),
        )
    raise last_err
