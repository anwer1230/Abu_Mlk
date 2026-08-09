---
name: Telegram session lookup
description: Durable constraint for connecting authenticated Telegram users to chat API calls.
---

Authentication creates a portable StringSession keyed by the Telegram user ID, while some legacy flows also create phone-number session files. Chat and message API helpers must prefer the user-ID StringSession and only fall back to a file session.

**Why:** Choosing only a phone-number-derived session can make a successful login appear empty or unauthenticated immediately afterward.

**How to apply:** When adding or changing Telethon request helpers, resolve the StringSession first, validate authorization, and close the client/event loop cleanly after the request.