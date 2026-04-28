"""Python bridge for the free-code CLI stream-json protocol.

This client talks to the existing headless CLI mode:

    --print --input-format stream-json --output-format stream-json --verbose

It is intended for web backends that want to drive the CLI process directly
through stdin/stdout instead of interactive terminal input.
"""

from __future__ import annotations

import json
import os
import queue
import shutil
import subprocess
import threading
import time
import uuid
from collections import deque
from pathlib import Path
from typing import Any, Callable, Deque, Dict, Iterable, Iterator, List, Optional


JsonDict = Dict[str, Any]
PermissionHandler = Callable[[JsonDict], Optional[JsonDict]]
_STDOUT_SENTINEL = object()


class FreeCodeCliError(RuntimeError):
    """Base error raised by the Python bridge."""


class FreeCodeCliProtocolError(FreeCodeCliError):
    """Raised when the CLI writes invalid NDJSON to stdout."""


class FreeCodeCliExitedError(FreeCodeCliError):
    """Raised when the CLI exits before the caller expected it to."""


def extract_assistant_text(event: JsonDict) -> str:
    """Best-effort extraction of text from an assistant event."""

    if event.get("type") == "assistant_partial":
        return str(event.get("delta") or "")

    message = event.get("message")
    if not isinstance(message, dict):
        return ""

    content = message.get("content")
    if isinstance(content, str):
        return content

    if not isinstance(content, list):
        return ""

    chunks: List[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text":
            text = block.get("text")
            if isinstance(text, str):
                chunks.append(text)
    return "".join(chunks)


class FreeCodeCliClient:
    """Small process wrapper around the CLI stream-json mode."""

    def __init__(
        self,
        cli_path: Optional[str] = None,
        *,
        cwd: Optional[str] = None,
        extra_args: Optional[Iterable[str]] = None,
        env: Optional[Dict[str, str]] = None,
        session_id: Optional[str] = None,
        auto_start: bool = False,
        auto_permission_handler: Optional[PermissionHandler] = None,
        stderr_max_lines: int = 200,
    ) -> None:
        self.repo_root = Path(__file__).resolve().parents[1]
        self.cli_path = self._resolve_cli_path(cli_path)
        self.cwd = str(Path(cwd).resolve()) if cwd else str(self.repo_root)
        self.extra_args = list(extra_args or [])
        self.env_overrides = dict(env or {})
        self.session_id = session_id or str(uuid.uuid4())
        self.auto_permission_handler = auto_permission_handler
        self.stderr_lines: Deque[str] = deque(maxlen=stderr_max_lines)

        self.process: Optional[subprocess.Popen[str]] = None
        self._stdout_thread: Optional[threading.Thread] = None
        self._stderr_thread: Optional[threading.Thread] = None
        self._events: "queue.Queue[object]" = queue.Queue()
        self._write_lock = threading.Lock()

        if auto_start:
            self.start()

    @staticmethod
    def _resolve_cli_path(cli_path: Optional[str]) -> str:
        if cli_path:
            return str(Path(cli_path).expanduser().resolve())

        env_cli = os.environ.get("FREE_CODE_CLI")
        if env_cli:
            return str(Path(env_cli).expanduser().resolve())

        repo_root = Path(__file__).resolve().parents[1]
        local_candidates = [
            repo_root / "cli",
            repo_root / "cli-dev",
            repo_root / "dist" / "cli",
        ]
        for candidate in local_candidates:
            if candidate.exists():
                return str(candidate.resolve())

        for name in ("free-code", "claude", "claude-source"):
            resolved = shutil.which(name)
            if resolved:
                return resolved

        searched = ", ".join(str(path) for path in local_candidates)
        raise FileNotFoundError(
            "Cannot find the CLI executable. Set --cli or FREE_CODE_CLI, "
            f"or build the project first. Tried: {searched}"
        )

    def build_command(self) -> List[str]:
        return [
            self.cli_path,
            "--print",
            "--verbose",
            "--input-format",
            "stream-json",
            "--output-format",
            "stream-json",
            "--session-id",
            self.session_id,
            *self.extra_args,
        ]

    def start(self) -> None:
        if self.process and self.process.poll() is None:
            return

        print(f"[free-code] Starting CLI: {self.cli_path}")
        print(f"[free-code] Working directory: {self.cwd}")
        print(f"[free-code] Extra args: {self.extra_args}")

        env = os.environ.copy()
        env.update(self.env_overrides)

        self.process = subprocess.Popen(
            self.build_command(),
            cwd=self.cwd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,
            env=env,
        )

        self._stdout_thread = threading.Thread(
            target=self._stdout_reader,
            name="free-code-stdout-reader",
            daemon=True,
        )
        self._stderr_thread = threading.Thread(
            target=self._stderr_reader,
            name="free-code-stderr-reader",
            daemon=True,
        )
        self._stdout_thread.start()
        self._stderr_thread.start()

    def _stdout_reader(self) -> None:
        assert self.process is not None
        assert self.process.stdout is not None

        try:
            for raw_line in self.process.stdout:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError as exc:
                    self._events.put(
                        FreeCodeCliProtocolError(
                            f"Invalid JSON line from CLI stdout: {line}"
                        )
                    )
                    self._events.put(_STDOUT_SENTINEL)
                    return
                self._events.put(payload)
        finally:
            self._events.put(_STDOUT_SENTINEL)

    def _stderr_reader(self) -> None:
        assert self.process is not None
        assert self.process.stderr is not None

        for raw_line in self.process.stderr:
            line = raw_line.rstrip("\n")
            if line:
                self.stderr_lines.append(line)

    def _ensure_started(self) -> None:
        if not self.process:
            self.start()

    def _ensure_running(self) -> None:
        self._ensure_started()
        assert self.process is not None
        if self.process.poll() is not None:
            raise FreeCodeCliExitedError(self._build_exit_message())

    def _build_exit_message(self) -> str:
        if not self.process:
            return "CLI process is not started."
        code = self.process.poll()
        stderr_tail = "\n".join(self.stderr_lines)
        message = f"CLI process exited with code {code}."
        if stderr_tail:
            message += f"\nLast stderr lines:\n{stderr_tail}"
        return message

    def send(self, payload: JsonDict) -> None:
        self._ensure_running()
        assert self.process is not None
        assert self.process.stdin is not None

        line = json.dumps(payload, ensure_ascii=False)
        with self._write_lock:
            self.process.stdin.write(line + "\n")
            self.process.stdin.flush()

    def send_user_message(
        self,
        content: Any,
        *,
        priority: Optional[str] = None,
        message_uuid: Optional[str] = None,
        parent_tool_use_id: Optional[str] = None,
    ) -> str:
        message_uuid = message_uuid or str(uuid.uuid4())
        payload: JsonDict = {
            "type": "user",
            "message": {
                "role": "user",
                "content": content,
            },
            "parent_tool_use_id": parent_tool_use_id,
            "session_id": self.session_id,
            "uuid": message_uuid,
        }
        if priority:
            payload["priority"] = priority
        self.send(payload)
        return message_uuid

    def send_text(
        self,
        text: str,
        *,
        priority: Optional[str] = None,
        message_uuid: Optional[str] = None,
    ) -> str:
        return self.send_user_message(
            text,
            priority=priority,
            message_uuid=message_uuid,
        )

    def send_control_request(
        self,
        subtype: str,
        **request_fields: Any,
    ) -> str:
        request_id = str(uuid.uuid4())
        payload: JsonDict = {
            "type": "control_request",
            "request_id": request_id,
            "request": {
                "subtype": subtype,
                **request_fields,
            },
        }
        self.send(payload)
        return request_id

    def send_control_response_success(
        self,
        request_id: str,
        response: Optional[JsonDict] = None,
    ) -> None:
        payload: JsonDict = {
            "type": "control_response",
            "response": {
                "subtype": "success",
                "request_id": request_id,
            },
        }
        if response is not None:
            payload["response"]["response"] = response
        self.send(payload)

    def send_control_response_error(self, request_id: str, error: str) -> None:
        self.send(
            {
                "type": "control_response",
                "response": {
                    "subtype": "error",
                    "request_id": request_id,
                    "error": error,
                },
            }
        )

    def allow_tool(self, request_id: str, updated_input: Optional[JsonDict] = None) -> None:
        response: JsonDict = {"behavior": "allow"}
        if updated_input is not None:
            response["updatedInput"] = updated_input
        self.send_control_response_success(request_id, response)

    def deny_tool(self, request_id: str, message: str = "Denied by Python bridge") -> None:
        self.send_control_response_success(
            request_id,
            {
                "behavior": "deny",
                "message": message,
            },
        )

    def interrupt(self) -> str:
        return self.send_control_request("interrupt")

    def end_session(self, reason: str = "python_client_closed") -> str:
        return self.send_control_request("end_session", reason=reason)

    def read_event(self, timeout: Optional[float] = None) -> JsonDict:
        self._ensure_started()

        try:
            item = self._events.get(timeout=timeout)
        except queue.Empty as exc:
            raise TimeoutError("Timed out waiting for CLI event.") from exc

        if item is _STDOUT_SENTINEL:
            raise FreeCodeCliExitedError(self._build_exit_message())

        if isinstance(item, Exception):
            raise item

        event = item
        assert isinstance(event, dict)

        if (
            self.auto_permission_handler
            and event.get("type") == "control_request"
            and isinstance(event.get("request"), dict)
            and event["request"].get("subtype") == "can_use_tool"
        ):
            request_id = event.get("request_id")
            if isinstance(request_id, str):
                response = self.auto_permission_handler(event)
                if response is not None:
                    self.send_control_response_success(request_id, response)

        return event

    def iter_events(self, timeout: Optional[float] = None) -> Iterator[JsonDict]:
        while True:
            yield self.read_event(timeout=timeout)

    def collect_until_result(
        self,
        *,
        timeout: Optional[float] = None,
        on_event: Optional[Callable[[JsonDict], None]] = None,
    ) -> List[JsonDict]:
        events: List[JsonDict] = []
        deadline = None if timeout is None else time.monotonic() + timeout

        while True:
            remaining = None if deadline is None else max(0.0, deadline - time.monotonic())
            event = self.read_event(timeout=remaining)
            events.append(event)

            if on_event:
                on_event(event)

            if event.get("type") == "result":
                return events

    def ask(
        self,
        text: str,
        *,
        timeout: Optional[float] = None,
        priority: Optional[str] = None,
        on_event: Optional[Callable[[JsonDict], None]] = None,
    ) -> List[JsonDict]:
        self.send_text(text, priority=priority)
        return self.collect_until_result(timeout=timeout, on_event=on_event)

    def wait(self, timeout: Optional[float] = None) -> int:
        if not self.process:
            raise FreeCodeCliError("CLI process is not started.")
        return self.process.wait(timeout=timeout)

    def close(self, *, terminate_timeout: float = 5.0) -> None:
        if not self.process:
            return

        if self.process.poll() is None:
            try:
                self.end_session()
            except FreeCodeCliError:
                pass
            except BrokenPipeError:
                pass

        if self.process.stdin:
            try:
                self.process.stdin.close()
            except OSError:
                pass

        if self.process.poll() is None:
            try:
                self.process.wait(timeout=terminate_timeout)
            except subprocess.TimeoutExpired:
                self.process.terminate()
                try:
                    self.process.wait(timeout=2.0)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=2.0)

    def __enter__(self) -> "FreeCodeCliClient":
        self.start()
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.close()
