# مركز سرعة إنجاز

تطبيق ويب متكامل لإدارة محادثات تيليجرام، مبني على Flask + Socket.IO + Telethon. يتيح تسجيل الدخول بحساب تيليجرام الحقيقي، واستقبال الرسائل وإرسالها في الوقت الفعلي من المتصفح.

## Run & Operate

- `Flask App` — الـ workflow الرئيسي (يشغّل main.py على port 5000)
- Python venv: `/home/runner/workspace/.venv/bin/python`
- قاعدة البيانات: `database.db` (SQLite محلية)

## Stack

- Python 3.13 + Flask 3 + Flask-SocketIO 5
- Telethon 1.44 (عميل تيليجرام)
- SQLite (قاعدة بيانات محلية)
- Socket.IO (اتصال ثنائي الاتجاه في الوقت الفعلي)
- Bootstrap 5 RTL + Tajawal Font

## Where Things Live

- `app.py` — التطبيق الرئيسي (Flask routes + Socket.IO events)
- `auth.py` — نظام المصادقة عبر Telethon (send_code → verify_code → 2FA)
- `database.py` — طبقة البيانات (SQLite + GitHub backup)
- `config.py` — الإعدادات المركزية (API keys, paths, etc.)
- `bot_manager.py` — إدارة البوتات (أوامر، callbacks، state machine)
- `upload_handler.py` — رفع الملفات بالأجزاء (Chunked upload)
- `github_db.py` — مزامنة البيانات مع GitHub
- `templates/` — صفحات HTML (Jinja2)
- `static/` — CSS + JS
- `sessions/` — ملفات جلسات Telethon لكل مستخدم

## Architecture Decisions

- كل مستخدم له Telethon client منفصل يعمل في thread مستقل
- Socket.IO rooms: `user_{id}` للمستخدم الفردي، `chat_{id}` للمحادثة
- StringSession لحفظ جلسات Telethon بدون إعادة تسجيل الدخول
- GitHub كقاعدة بيانات احتياطية دائمة عبر github_db.py
- eventlet كـ async mode لـ Flask-SocketIO

## Environment Variables

- `SESSION_SECRET` — مفتاح جلسة Flask (متوفر)
- `TDLIB_API_ID` — معرف Telegram API (مضمّن افتراضياً)
- `TDLIB_API_HASH` — هاش Telegram API (مضمّن افتراضياً)
- `GITHUB_TOKEN` — للمزامنة مع GitHub (اختياري)

## User Preferences

- اللغة العربية RTL
- الواجهة الداكنة (Dark theme)
