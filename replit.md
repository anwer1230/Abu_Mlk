# مركز سرعة إنجاز — Abu_Mlk

تطبيق خدمات طلابية وأكاديمية مبني على Flask + SocketIO مع تكامل Telegram.

## Run & Operate

- `python main.py` — تشغيل التطبيق (المنفذ 5000)
- **Workflow:** Flask App (يعمل على المنفذ 5000)
- المستودع الأصلي: https://github.com/anwer1230/Abu_Mlk

## Stack

- Python 3.13 + Flask 3 + Flask-SocketIO
- SQLite (قاعدة بيانات محلية) + مزامنة GitHub
- Telethon (Telegram API)
- Groq AI

## Where things live

- `main.py` — نقطة الدخول الرئيسية
- `app.py` — التطبيق الرئيسي (Flask routes + SocketIO)
- `auth.py` — نظام المصادقة عبر Telegram
- `database.py` — قاعدة البيانات SQLite
- `config.py` — الإعدادات المركزية
- `bot_manager.py` — إدارة البوتات
- `upload_handler.py` — رفع الملفات
- `github_db.py` — تخزين البيانات على GitHub
- `card_system.py` — نظام البطاقات والقسائم
- `gps_tracking.py` — تتبع الموقع الجغرافي
- `install_tracker.py` — تتبع التثبيتات
- `isolation_system.py` — عزل بيانات المستخدمين
- `templates/` — قوالب HTML
- `static/` — CSS + JS + صور
- `sessions/` — جلسات المستخدمين
- `data/` — بيانات JSON

## Environment Variables (required)

- `SESSION_SECRET` — مفتاح الجلسة (مضبوط)
- `GITHUB_TOKEN` — رمز GitHub للمزامنة (اختياري)
- `GROQ_API_KEY` — مفتاح Groq AI (اختياري)

## User preferences

_Populate as you build._

## Gotchas

- تثبيت الحزم: `pip install --break-system-packages --user -r requirements.txt`
- التطبيق يعمل على المنفذ 5000
