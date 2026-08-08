"""TDLib session and the small application-facing command surface."""

from __future__ import annotations

import os
import secrets
import threading
from pathlib import Path
from typing import Any

from tdjson_client import TdJsonClient


class TelegramService:
    def __init__(self) -> None:
        api_id = os.environ.get("TELEGRAM_API_ID")
        api_hash = os.environ.get("TELEGRAM_API_HASH")
        if not api_id or not api_hash:
            raise RuntimeError("TELEGRAM_API_ID and TELEGRAM_API_HASH are required")
        self._client = TdJsonClient(
            int(api_id),
            api_hash,
            os.environ.get(
                "TELEGRAM_DATABASE_DIRECTORY",
                str(Path(__file__).resolve().parents[1] / ".telegram-data"),
            ),
        )
        self._updates: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self._client.start()
        self._drain_thread = threading.Thread(target=self._drain, daemon=True)
        self._drain_thread.start()

    def _drain(self) -> None:
        while True:
            update = self._client.receive(1.0)
            if update is None:
                continue
            with self._lock:
                self._updates.append(update)
                del self._updates[:-500]

    def state(self) -> dict[str, Any]:
        with self._lock:
            updates = list(self._updates)
        auth = next(
            (
                item.get("authorization_state", {})
                for item in reversed(updates)
                if item.get("@type") == "updateAuthorizationState"
            ),
            {"@type": "authorizationStateWaitTdlibParameters"},
        )
        return {"authorization_state": auth, "updates": updates[-50:]}

    def start_auth(self, phone_number: str) -> None:
        self._client.send(
            {
                "@type": "setAuthenticationPhoneNumber",
                "phone_number": phone_number,
                "settings": {"@type": "phoneNumberAuthenticationSettings"},
            }
        )

    def verify_code(self, code: str) -> None:
        self._client.send({"@type": "checkAuthenticationCode", "code": code})

    def verify_password(self, password: str) -> None:
        self._client.send(
            {"@type": "checkAuthenticationPassword", "password": password}
        )

    def chats(self, limit: int = 100) -> dict[str, Any] | None:
        return self._client.execute(
            {
                "@type": "getChats",
                "chat_list": {"@type": "chatListMain"},
                "limit": max(1, min(limit, 100)),
            }
        )

    def chat(self, chat_id: int) -> dict[str, Any] | None:
        return self._client.execute({"@type": "getChat", "chat_id": chat_id})

    def history(self, chat_id: int, limit: int = 50) -> dict[str, Any] | None:
        return self._client.execute(
            {
                "@type": "getChatHistory",
                "chat_id": chat_id,
                "from_message_id": 0,
                "offset": 0,
                "limit": max(1, min(limit, 100)),
                "only_local": False,
            }
        )

    def send_text(self, chat_id: int, text: str) -> dict[str, Any] | None:
        self._client.send(
            {
                "@type": "sendMessage",
                "chat_id": chat_id,
                "input_message_content": {
                    "@type": "inputMessageText",
                    "text": {
                        "@type": "formattedText",
                        "text": text,
                        "entities": [],
                    },
                },
            }
        )

    def raw(self, query: dict[str, Any]) -> None:
        query.setdefault("@extra", secrets.token_hex(8))
        self._client.send(query)