"""
auth.py — مركز سرعة إنجاز
╔══════════════════════════════════════════════════════════════╗
║   نظام تسجيل الدخول وإدارة الجلسات لكل مستخدم بشكل منفصل   ║
║   يستخدم Telethon + StringSession + GitHub كقاعدة بيانات    ║
║   المستودع الأصلي: https://github.com/anwer1230/Abu_Mlk     ║
╚══════════════════════════════════════════════════════════════╝
"""

import os
import json
import asyncio
import logging
import threading
import hashlib
import time
from functools import wraps
from flask import session, jsonify

logger = logging.getLogger('auth')

# ── إعدادات Telegram API (من المستودع الأصلي) ─────────────────
API_ID   = os.environ.get('TDLIB_API_ID',   '22043994')
API_HASH = os.environ.get('TDLIB_API_HASH', '56f64582b363d367280db96586b97801')

# ── مسار مجلد الجلسات ──────────────────────────────────────
SESSIONS_DIR = os.path.join('/tmp', 'sessions') if os.environ.get('RENDER') else "sessions"
os.makedirs(SESSIONS_DIR, exist_ok=True)


# ══════════════════════════════════════════════════════════════
#  وظائف إدارة ملفات الجلسة — كل مستخدم له مجلده الخاص
# ══════════════════════════════════════════════════════════════

def get_user_session_dir(user_id: str) -> str:
    """إرجاع مسار المجلد الخاص بالمستخدم، ويُنشئه إن لم يكن موجوداً"""
    user_dir = os.path.join(SESSIONS_DIR, str(user_id))
    os.makedirs(user_dir, exist_ok=True)
    return user_dir


def save_settings(user_id: str, settings: dict) -> bool:
    """حفظ إعدادات المستخدم في مجلده الخاص + نسخة احتياطية"""
    try:
        user_dir = get_user_session_dir(user_id)
        path = os.path.join(user_dir, "settings.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=4)
        # نسخة احتياطية للتوافق مع الكود القديم
        legacy_path = os.path.join(SESSIONS_DIR, f"{user_id}.json")
        with open(legacy_path, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=4)
        return True
    except Exception as e:
        logger.error(f"Error saving settings for {user_id}: {e}")
        return False


def load_settings(user_id: str) -> dict:
    """تحميل إعدادات المستخدم — يبحث أولاً في مجلده، ثم الملف القديم"""
    try:
        user_dir = get_user_session_dir(user_id)
        path = os.path.join(user_dir, "settings.json")
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        legacy_path = os.path.join(SESSIONS_DIR, f"{user_id}.json")
        if os.path.exists(legacy_path):
            with open(legacy_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            save_settings(user_id, data)
            return data
        return {}
    except Exception as e:
        logger.error(f"Error loading settings for {user_id}: {e}")
        return {}


def clear_user_session(user_id: str) -> bool:
    """حذف جميع ملفات الجلسة الخاصة بالمستخدم"""
    try:
        import shutil
        user_dir = get_user_session_dir(user_id)
        if os.path.exists(user_dir):
            shutil.rmtree(user_dir)
        for suffix in [".json", "_session.session", "_string.txt"]:
            p = os.path.join(SESSIONS_DIR, f"{user_id}{suffix}")
            if os.path.exists(p):
                os.remove(p)
        logger.info(f"Cleared session for {user_id}")
        return True
    except Exception as e:
        logger.error(f"Error clearing session for {user_id}: {e}")
        return False


def save_string_session(user_id: str, session_str: str) -> None:
    """حفظ سلسلة StringSession في ملف نصي خاص بالمستخدم"""
    try:
        os.makedirs(SESSIONS_DIR, exist_ok=True)
        path = os.path.join(SESSIONS_DIR, f"{user_id}_string.txt")
        with open(path, 'w') as f:
            f.write(session_str)
        logger.info(f"Saved StringSession for {user_id}")
    except Exception as e:
        logger.error(f"Error saving StringSession for {user_id}: {e}")


def load_string_session(user_id: str) -> str | None:
    """تحميل سلسلة StringSession"""
    path = os.path.join(SESSIONS_DIR, f"{user_id}_string.txt")
    if os.path.exists(path):
        try:
            with open(path, 'r') as f:
                return f.read().strip()
        except Exception as e:
            logger.error(f"Error loading StringSession for {user_id}: {e}")
    return None


# ══════════════════════════════════════════════════════════════
#  TelegramLogin — واجهة تسجيل الدخول عبر Telethon
# ══════════════════════════════════════════════════════════════

class TelegramLogin:
    """
    يدير دورة حياة تسجيل الدخول:
      phone → send_code → verify_code → (optionally) verify_password → authenticated
    كل كائن يخدم رقم هاتف واحد ويعمل على loop خاص به في thread منفصل.
    """

    def __init__(self, phone: str):
        self.phone             = phone
        self.client            = None
        self.loop              = None
        self._thread           = None
        self.awaiting_code     = False
        self.awaiting_password = False
        self.authenticated     = False
        self._started          = threading.Event()
        self._error: str | None = None

    # ── بدء التشغيل الداخلي ────────────────────────────────────

    def _run_loop(self):
        """يشغّل event loop في thread منفصل."""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self._started.set()
        self.loop.run_forever()

    def _ensure_running(self):
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run_loop, daemon=True,
                                        name=f"tg-loop-{self.phone[-4:]}")
        self._thread.start()
        self._started.wait(timeout=5)

    def _run(self, coro, timeout=30):
        """تنفيذ coroutine على loop التشغيل الداخلي."""
        self._ensure_running()
        future = asyncio.run_coroutine_threadsafe(coro, self.loop)
        return future.result(timeout=timeout)

    # ── الخطوة 1: إرسال الكود ──────────────────────────────────

    def send_code(self) -> dict:
        """يُنشئ عميل Telethon ويطلب إرسال كود التحقق."""
        try:
            from telethon import TelegramClient
            from telethon.sessions import StringSession

            self._ensure_running()

            session_path = os.path.join(SESSIONS_DIR, f"{self.phone.replace('+','')}")

            async def _send():
                client = TelegramClient(
                    session_path,
                    int(API_ID),
                    API_HASH,
                    loop=self.loop,
                )
                await client.connect()
                self.client = client
                result = await client.send_code_request(self.phone)
                self.awaiting_code = True
                return result

            self._run(_send(), timeout=40)
            return {"success": True, "message": "✅ تم إرسال كود التحقق إلى هاتفك عبر تليجرام"}
        except Exception as e:
            error_msg = str(e)
            logger.error(f"send_code error for {self.phone}: {error_msg}")
            if "Too Many Requests" in error_msg or "FLOOD" in error_msg.upper():
                return {"success": False, "message": "⏳ طلبات كثيرة، انتظر قليلاً ثم أعد المحاولة"}
            if "PHONE_NUMBER_INVALID" in error_msg:
                return {"success": False, "message": "❌ رقم الهاتف غير صحيح"}
            return {"success": False, "message": f"❌ خطأ: {error_msg}"}

    # ── الخطوة 2: التحقق من الكود ──────────────────────────────

    def verify_code(self, code: str) -> dict:
        """التحقق من كود التحقق المرسل."""
        if not self.awaiting_code:
            return {"success": False, "message": "لم يتم طلب كود بعد، أرسل الكود أولاً"}
        if not self.client:
            return {"success": False, "message": "العميل غير متصل"}

        try:
            async def _verify():
                from telethon import TelegramClient
                me = await self.client.sign_in(self.phone, code)
                return me

            me = self._run(_verify(), timeout=40)
            self.awaiting_code     = False
            self.awaiting_password = False
            self.authenticated     = True

            # حفظ StringSession
            async def _get_session():
                from telethon.sessions import StringSession
                return StringSession.save(self.client.session)

            session_str = self._run(_get_session(), timeout=10)
            save_string_session(str(me.id), session_str)

            return {
                "success": True,
                "message": "✅ تم تسجيل الدخول بنجاح",
                "user": {
                    "id":         me.id,
                    "first_name": me.first_name,
                    "last_name":  me.last_name,
                    "username":   me.username,
                    "phone":      me.phone,
                    "full_name":  f"{me.first_name or ''} {me.last_name or ''}".strip()
                }
            }
        except Exception as e:
            error_msg = str(e)
            logger.error(f"verify_code error: {error_msg}")
            if "PASSWORD" in error_msg.upper() or "SESSION_PASSWORD_NEEDED" in error_msg:
                self.awaiting_password = True
                self.awaiting_code     = False
                return {
                    "success":          False,
                    "requires_password": True,
                    "message":          "🔐 هذا الحساب محمي بالتحقق بخطوتين. الرجاء إدخال كلمة المرور"
                }
            if "PHONE_CODE_INVALID" in error_msg:
                return {"success": False, "message": "❌ الكود غير صحيح"}
            if "PHONE_CODE_EXPIRED" in error_msg:
                return {"success": False, "message": "❌ انتهت صلاحية الكود، أعد الإرسال"}
            return {"success": False, "message": f"❌ كود غير صحيح: {error_msg}"}

    # ── الخطوة 3: التحقق من كلمة المرور (2FA) ─────────────────

    def verify_password(self, password: str) -> dict:
        """التحقق من كلمة مرور التحقق الثنائي."""
        if not self.awaiting_password:
            return {"success": False, "message": "الحساب لا يتطلب كلمة مرور"}
        if not self.client:
            return {"success": False, "message": "العميل غير متصل"}

        try:
            async def _check_pw():
                me = await self.client.sign_in(password=password)
                return me

            me = self._run(_check_pw(), timeout=40)
            self.awaiting_password = False
            self.authenticated     = True

            async def _get_session():
                from telethon.sessions import StringSession
                return StringSession.save(self.client.session)

            session_str = self._run(_get_session(), timeout=10)
            save_string_session(str(me.id), session_str)

            return {
                "success": True,
                "message": "✅ تم تسجيل الدخول بنجاح",
                "user": {
                    "id":         me.id,
                    "first_name": me.first_name,
                    "last_name":  me.last_name,
                    "username":   me.username,
                    "phone":      me.phone,
                    "full_name":  f"{me.first_name or ''} {me.last_name or ''}".strip()
                }
            }
        except Exception as e:
            error_msg = str(e)
            if "PASSWORD_HASH_INVALID" in error_msg or "invalid" in error_msg.lower():
                return {"success": False, "message": "❌ كلمة المرور غير صحيحة"}
            return {"success": False, "message": f"❌ خطأ: {error_msg}"}

    def disconnect(self):
        """قطع الاتصال وإيقاف loop."""
        try:
            if self.client and self.loop and self.loop.is_running():
                asyncio.run_coroutine_threadsafe(self.client.disconnect(), self.loop)
            if self.loop:
                self.loop.call_soon_threadsafe(self.loop.stop)
        except Exception:
            pass


# ══════════════════════════════════════════════════════════════
#  AuthManager — المدير العام لجلسات المصادقة
# ══════════════════════════════════════════════════════════════

class AuthManager:
    """
    يدير كل جلسات تسجيل الدخول النشطة (phone → TelegramLogin)
    ويوفر ديكور login_required وطرق مساعدة للتطبيق.
    """

    def __init__(self, db=None):
        self.db            = db
        self.pending: dict = {}        # {phone: TelegramLogin}
        self._lock         = threading.Lock()
        # تنظيف الجلسات المنتهية كل 10 دقائق
        self._start_cleanup()

    # ── ديكور ─────────────────────────────────────────────────

    def login_required(self, f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not self.is_authenticated():
                return jsonify({'success': False, 'message': 'يرجى تسجيل الدخول'}), 401
            return f(*args, **kwargs)
        return decorated

    # ── إرسال الكود ───────────────────────────────────────────

    def send_code(self, phone: str) -> dict:
        phone = phone.strip()
        if not phone.startswith('+'):
            phone = '+' + phone
        with self._lock:
            # إلغاء جلسة سابقة للرقم نفسه إن وُجدت
            if phone in self.pending:
                try:
                    self.pending[phone].disconnect()
                except Exception:
                    pass
            login = TelegramLogin(phone)
            result = login.send_code()
            if result.get('success'):
                self.pending[phone] = login
        return result

    # ── التحقق من الكود ──────────────────────────────────────

    def check_code(self, phone: str, code: str) -> dict:
        phone = phone.strip()
        if not phone.startswith('+'):
            phone = '+' + phone
        with self._lock:
            login = self.pending.get(phone)
        if not login:
            return {'success': False, 'message': 'انتهت الجلسة، أرسل الكود مجدداً'}

        result = login.verify_code(code.strip())
        if result.get('success'):
            self._on_login_success(phone, result['user'], login)
        return result

    # ── التحقق من كلمة المرور (2FA) ──────────────────────────

    def check_password(self, phone: str, password: str) -> dict:
        phone = phone.strip()
        if not phone.startswith('+'):
            phone = '+' + phone
        with self._lock:
            login = self.pending.get(phone)
        if not login:
            return {'success': False, 'message': 'انتهت الجلسة، ابدأ من جديد'}
        if not login.awaiting_password:
            return {'success': False, 'message': 'الحساب لا يتطلب كلمة مرور'}

        result = login.verify_password(password)
        if result.get('success'):
            self._on_login_success(phone, result['user'], login)
        return result

    # ── بعد تسجيل الدخول الناجح ────────────────────────────────

    def _on_login_success(self, phone: str, user_info: dict, login: TelegramLogin):
        user_id   = str(user_info['id'])
        user_name = user_info.get('full_name') or user_info.get('first_name', '')

        # حفظ المستخدم في قاعدة البيانات
        if self.db:
            try:
                self.db.upsert_user(
                    user_id=user_id,
                    phone=phone,
                    name=user_name,
                    username=user_info.get('username'),
                )
                # نسخة احتياطية إلى GitHub
                threading.Thread(
                    target=self.db.backup_to_github,
                    args=(user_id,),
                    daemon=True
                ).start()
            except Exception as e:
                logger.error(f"DB upsert error: {e}")

        # حفظ بيانات الجلسة في Flask session
        session['user_id']         = user_id
        session['phone']           = phone
        session['user_name']       = user_name
        session['is_authenticated'] = True

        # حذف من pending بعد نجاح تسجيل الدخول
        with self._lock:
            self.pending.pop(phone, None)

        logger.info(f"✅ تسجيل دخول ناجح — {user_id} ({phone})")

    # ── تسجيل الخروج ────────────────────────────────────────────

    def logout(self) -> dict:
        session.clear()
        return {'success': True, 'message': 'تم تسجيل الخروج بنجاح'}

    # ── حالة المصادقة ────────────────────────────────────────────

    def is_authenticated(self) -> bool:
        return bool(session.get('is_authenticated') and session.get('user_id'))

    def get_user_info(self, user_id: str = None) -> dict | None:
        uid = user_id or session.get('user_id')
        if not uid or not self.db:
            return None
        return self.db.get_user(uid)

    def get_all_users(self) -> list:
        if not self.db:
            return []
        return self.db.get_all_users()

    # ── تنظيف الجلسات القديمة ────────────────────────────────────

    def _cleanup(self):
        while True:
            time.sleep(600)
            with self._lock:
                for phone in list(self.pending.keys()):
                    self.pending.pop(phone)

    def _start_cleanup(self):
        t = threading.Thread(target=self._cleanup, daemon=True, name="auth-cleanup")
        t.start()


# ══════════════════════════════════════════════════════════════
#  إدارة حسابات منصة المستخدمين الديناميكية
#  (متوافق مع app.py الأصلي)
# ══════════════════════════════════════════════════════════════

import hashlib as _hashlib
import json as _json

_DYN_DIR           = SESSIONS_DIR
_DYN_USERS_FILE    = os.path.join(_DYN_DIR, "dynamic_users.json")
_USER_ACCOUNTS_FILE = os.path.join(_DYN_DIR, "user_accounts.json")
_DYN_LOCK          = threading.Lock()
_ACCTS_LOCK        = threading.Lock()


def _dyn_github_params():
    from config import Config
    return Config.GITHUB_TOKEN, Config.GITHUB_REPO, Config.GITHUB_BRANCH


def _dyn_upload_github(repo_path, content, token, repo, branch, msg):
    """رفع ملف إلى GitHub بشكل بسيط."""
    if not token:
        return
    try:
        from github_db import gh_save
        data = _json.loads(content) if isinstance(content, bytes) else _json.loads(content)
        gh_save(repo_path, None, data, commit_msg=msg)
    except Exception as e:
        logger.debug(f"_dyn_upload_github: {e}")


def load_dynamic_users():
    with _DYN_LOCK:
        if os.path.exists(_DYN_USERS_FILE):
            try:
                with open(_DYN_USERS_FILE, 'r', encoding='utf-8') as f:
                    return _json.load(f)
            except Exception:
                pass
        return {}


def save_dynamic_users(users):
    with _DYN_LOCK:
        content = _json.dumps(users, ensure_ascii=False, indent=2).encode('utf-8')
        try:
            with open(_DYN_USERS_FILE, 'w', encoding='utf-8') as f:
                f.write(content.decode('utf-8'))
        except Exception:
            pass
        token, repo, branch = _dyn_github_params()
        _dyn_upload_github("data/dynamic_users.json", content, token, repo, branch,
                           "تحديث المستخدمين الديناميكيين")


def add_dynamic_user(user_id, phone, name=""):
    users = load_dynamic_users()
    users[str(user_id)] = {"user_id": str(user_id), "phone": phone,
                            "name": name, "active": True}
    save_dynamic_users(users)


def delete_dynamic_user(user_id):
    users = load_dynamic_users()
    users.pop(str(user_id), None)
    save_dynamic_users(users)


def load_user_accounts():
    with _ACCTS_LOCK:
        if os.path.exists(_USER_ACCOUNTS_FILE):
            try:
                with open(_USER_ACCOUNTS_FILE, 'r', encoding='utf-8') as f:
                    return _json.load(f)
            except Exception:
                pass
        return {}


def save_user_accounts(accounts):
    with _ACCTS_LOCK:
        content = _json.dumps(accounts, ensure_ascii=False, indent=2).encode('utf-8')
        try:
            with open(_USER_ACCOUNTS_FILE, 'w', encoding='utf-8') as f:
                f.write(content.decode('utf-8'))
        except Exception:
            pass
        token, repo, branch = _dyn_github_params()
        _dyn_upload_github("data/user_accounts.json", content, token, repo, branch,
                           "تحديث حسابات المستخدمين")


def authenticate_platform_user(username, password):
    """التحقق من بيانات الدخول — يعيد username أو None"""
    accounts = load_user_accounts()
    if username not in accounts:
        return None
    hashed = _hashlib.sha256(password.encode()).hexdigest()
    if accounts[username].get("password") == hashed:
        return username
    return None


def create_platform_account(username, password, role="user"):
    """إنشاء حساب جديد"""
    if len(username) < 3:
        return False, "اسم المستخدم يجب أن يكون 3 أحرف على الأقل"
    if len(password) < 6:
        return False, "كلمة المرور يجب أن تكون 6 أحرف على الأقل"
    accounts = load_user_accounts()
    if username in accounts:
        return False, "اسم المستخدم موجود مسبقاً"
    import datetime as _dt
    accounts[username] = {
        "username":   username,
        "password":   _hashlib.sha256(password.encode()).hexdigest(),
        "role":       role,
        "created_at": _dt.datetime.now().isoformat(),
    }
    save_user_accounts(accounts)
    return True, "تم إنشاء الحساب بنجاح"


def delete_platform_account(username):
    accounts = load_user_accounts()
    if username not in accounts:
        return False, "الحساب غير موجود"
    del accounts[username]
    save_user_accounts(accounts)
    return True, "تم حذف الحساب"
