# config.py — مركز سرعة إنجاز
# ═══════════════════════════════════════════════════════════════════════════
# ملف الإعدادات المركزي — يجمع كل الثوابت في مكان واحد
# المستودع الأصلي: https://github.com/anwer1230/Abu_Mlk
# ═══════════════════════════════════════════════════════════════════════════

import os
import secrets


class Config:
    # ── التطبيق ──────────────────────────────────────────────────────────
    SECRET_KEY  = os.environ.get('SESSION_SECRET') or secrets.token_hex(32)
    DEBUG       = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
    APP_TITLE   = "مركز سرعة إنجاز 📚 للخدمات الطلابية والأكاديمية"
    APP_VERSION = "2.0.0"

    # ── قاعدة البيانات (SQLite محلي) ────────────────────────────────────
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    DATABASE = os.path.join(BASE_DIR, 'database.db')

    # ── GitHub — المستودع الأساسي كقاعدة بيانات دائمة ────────────────────
    GITHUB_TOKEN  = os.environ.get('GITHUB_TOKEN', '')
    GITHUB_REPO   = 'anwer1230/Abu_Mlk'   # المستودع الرسمي للبرنامج
    GITHUB_BRANCH = 'main'

    # ── مجلدات التخزين ────────────────────────────────────────────────────
    SESSION_DIR = os.path.join(BASE_DIR, 'sessions')
    UPLOAD_DIR  = os.path.join(BASE_DIR, 'uploads')
    STATIC_DIR  = os.path.join(BASE_DIR, 'static')
    DATA_DIR    = os.path.join(BASE_DIR, 'data')
    TEMP_DIR    = os.path.join(BASE_DIR, 'uploads', 'temp')

    # ── إعدادات Telegram API (من المستودع الأصلي) ─────────────────────────
    TDLIB_API_ID   = int(os.environ.get('TDLIB_API_ID', '22043994'))
    TDLIB_API_HASH = os.environ.get('TDLIB_API_HASH', '56f64582b363d367280db96586b97801')

    # ── WebSocket / SocketIO ──────────────────────────────────────────────
    SOCKET_HOST = '0.0.0.0'
    SOCKET_PORT = int(os.environ.get('PORT', '5000'))

    # ── رفع الملفات ───────────────────────────────────────────────────────
    MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024   # 2 GB
    CHUNK_SIZE    = 1024 * 1024              # 1 MB

    # ── إعدادات الكاش ─────────────────────────────────────────────────────
    CACHE_TTL = 60   # ثانية

    @classmethod
    def ensure_dirs(cls):
        """إنشاء كل المجلدات المطلوبة إن لم تكن موجودة."""
        for d in (
            cls.SESSION_DIR,
            cls.UPLOAD_DIR,
            cls.TEMP_DIR,
            cls.DATA_DIR,
            cls.STATIC_DIR,
            os.path.join(cls.STATIC_DIR, 'css'),
            os.path.join(cls.STATIC_DIR, 'js'),
            os.path.join(cls.STATIC_DIR, 'icons'),
        ):
            os.makedirs(d, exist_ok=True)
