# Telegram backend

This folder is the real TDLib bridge used by the local app. It is deliberately
kept at the project root so the integration is easy to find.

- `tdjson_client.py` loads the official `libtdjson.so` through `ctypes`.
- `telegram_service.py` implements authentication, chats, history, and text
  messages using actual TDLib JSON methods.
- Telegram API credentials are read only from `TELEGRAM_API_ID` and
  `TELEGRAM_API_HASH`.

The generated native library is kept outside source control under
`.vendor/td-build/`. The browser must never receive the API hash.