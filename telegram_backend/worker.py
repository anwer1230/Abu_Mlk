"""Line-delimited JSON worker used by the TypeScript API server.

The process is intentionally tiny: the API server owns HTTP concerns while
this worker owns the long-lived native TDLib client and its local session.
"""

from __future__ import annotations

import json
import sys
from typing import Any

from telegram_service import TelegramService


def write_response(request_id: str, ok: bool, result: Any = None, error: str | None = None) -> None:
    payload: dict[str, Any] = {"id": request_id, "ok": ok}
    if ok:
        payload["result"] = result
    else:
        payload["error"] = error or "Telegram request failed"
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


try:
    service = TelegramService()
    startup_error: str | None = None
except Exception as exc:  # keep the worker alive so the API can report the real cause
    service = None
    startup_error = str(exc)

for line in sys.stdin:
    try:
        request = json.loads(line)
        request_id = str(request.get("id", "unknown"))
        method = request.get("method")
        params = request.get("params") or {}
        if startup_error:
            write_response(request_id, False, error=startup_error)
            continue
        if service is None:
            write_response(request_id, False, error="Telegram service is unavailable")
            continue

        if method == "state":
            result = service.state()
        elif method == "auth.start":
            service.start_auth(str(params["phone_number"]))
            result = {"status": "verification_requested"}
        elif method == "auth.code":
            service.verify_code(str(params["code"]))
            result = {"status": "code_submitted"}
        elif method == "auth.password":
            service.verify_password(str(params["password"]))
            result = {"status": "password_submitted"}
        elif method == "chats":
            result = service.chats(int(params.get("limit", 100)))
        elif method == "chat":
            result = service.chat(int(params["chat_id"]))
        elif method == "history":
            result = service.history(int(params["chat_id"]), int(params.get("limit", 50)))
        elif method == "send.text":
            service.send_text(int(params["chat_id"]), str(params["text"]))
            result = {"status": "sending"}
        else:
            write_response(request_id, False, error=f"Unsupported Telegram method: {method}")
            continue
        write_response(request_id, True, result=result)
    except Exception as exc:
        request_id = str(locals().get("request", {}).get("id", "unknown"))
        write_response(request_id, False, error=str(exc))