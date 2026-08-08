"""Small ctypes bridge for the official TDLib JSON shared library.

The uploaded files refer to a third-party ``tdjson`` Python package that is
not published at the requested version. TDLib itself exposes a stable C JSON
interface, so this module talks to the official ``libtdjson`` build directly.
"""

from __future__ import annotations

import ctypes
import json
import os
import threading
from ctypes import CFUNCTYPE, CDLL, POINTER, c_char_p, c_double, c_int
from pathlib import Path
from queue import Empty, Queue
from typing import Any


def _library_candidates() -> list[str]:
    configured = os.environ.get("TDJSON_LIBRARY")
    root = Path(__file__).resolve().parents[1]
    return [
        value
        for value in [
            configured,
            str(root / ".vendor/td-build/libtdjson.so"),
            str(root / ".vendor/td-build/libtdjson.so.1.8.66"),
            "libtdjson.so",
        ]
        if value
    ]


class TdJsonClient:
    def __init__(self, api_id: int, api_hash: str, database_directory: str):
        self.api_id = api_id
        self.api_hash = api_hash
        self.database_directory = database_directory
        self._updates: Queue[dict[str, Any]] = Queue()
        self._running = False
        self._receiver: threading.Thread | None = None
        self._library = self._load_library()
        self._configure_symbols()
        self.client_id = self._create_client_id()
        self._send(
            {
                "@type": "setTdlibParameters",
                "parameters": {
                    "database_directory": database_directory,
                    "files_directory": str(Path(database_directory) / "files"),
                    "use_file_database": True,
                    "use_chat_info_database": True,
                    "use_message_database": True,
                    "use_secret_chats": True,
                    "api_id": api_id,
                    "api_hash": api_hash,
                    "system_language_code": "en",
                    "device_model": "Telegram Local",
                    "application_version": "1.0",
                    "enable_storage_optimizer": True,
                },
            }
        )

    def _load_library(self) -> CDLL:
        errors: list[str] = []
        for candidate in _library_candidates():
            try:
                return CDLL(candidate)
            except OSError as error:
                errors.append(f"{candidate}: {error}")
        raise RuntimeError(
            "TDLib is not built or could not be loaded. " + " | ".join(errors)
        )

    def _configure_symbols(self) -> None:
        self._create_client_id = self._library.td_create_client_id
        self._create_client_id.restype = c_int
        self._create_client_id.argtypes = []

        self._send_native = self._library.td_send
        self._send_native.restype = None
        self._send_native.argtypes = [c_int, c_char_p]

        self._receive_native = self._library.td_receive
        self._receive_native.restype = c_char_p
        self._receive_native.argtypes = [c_double]

        self._execute_native = self._library.td_execute
        self._execute_native.restype = c_char_p
        self._execute_native.argtypes = [c_char_p]

        callback_type = CFUNCTYPE(None, c_int, c_char_p)

        @callback_type
        def log_callback(_verbosity: int, _message: bytes) -> None:
            return

        self._log_callback = log_callback
        self._set_log_callback = self._library.td_set_log_message_callback
        self._set_log_callback.restype = None
        self._set_log_callback.argtypes = [c_int, callback_type]
        self._set_log_callback(2, self._log_callback)

    def _send(self, query: dict[str, Any]) -> None:
        payload = json.dumps(query, separators=(",", ":")).encode("utf-8")
        self._send_native(self.client_id, payload)

    def send(self, query: dict[str, Any]) -> None:
        self._send(query)

    def execute(self, query: dict[str, Any]) -> dict[str, Any] | None:
        payload = json.dumps(query, separators=(",", ":")).encode("utf-8")
        result = self._execute_native(payload)
        if not result:
            return None
        return json.loads(result.decode("utf-8"))

    def start(self) -> None:
        if self._running:
            return
        self._running = True

        def receive_loop() -> None:
            while self._running:
                result = self._receive_native(1.0)
                if result:
                    self._updates.put(json.loads(result.decode("utf-8")))

        self._receiver = threading.Thread(target=receive_loop, daemon=True)
        self._receiver.start()

    def stop(self) -> None:
        self._running = False

    def receive(self, timeout: float = 0.1) -> dict[str, Any] | None:
        try:
            return self._updates.get(timeout=timeout)
        except Empty:
            return None