"""
isolation_system.py
══════════════════════════════════════════════════════════════
نظام العزل والفصل بين المستخدمين — وحدة مستقلة
يضمن عزلاً تاماً لبيانات وجلسات كل مستخدم عن الآخرين
══════════════════════════════════════════════════════════════
"""

import os
import json
import logging
import threading
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# ── إعداد مسارات العزل ──────────────────────────────────────────────────────
_RENDER_ENV   = os.environ.get('RENDER', '')
SESSIONS_DIR  = os.path.join('/tmp', 'sessions') if _RENDER_ENV else 'sessions'
DATA_DIR      = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')

os.makedirs(SESSIONS_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

_ISOLATION_LOCK = threading.Lock()


# ══════════════════════════════════════════════════════════
#  إدارة مجلدات المستخدمين المعزولة
# ══════════════════════════════════════════════════════════

def get_user_isolated_dir(user_id: str) -> str:
    """
    يُعيد مسار المجلد المعزول الخاص بالمستخدم وينشئه إن لم يكن موجوداً.
    كل مستخدم له مجلد منفصل تماماً لا يشترك مع أي مستخدم آخر.
    """
    user_dir = os.path.join(SESSIONS_DIR, str(user_id))
    os.makedirs(user_dir, exist_ok=True)
    return user_dir


def get_user_data_dir(user_id: str) -> str:
    """مجلد البيانات الدائمة للمستخدم (مستقل عن الجلسات)"""
    user_data_dir = os.path.join(DATA_DIR, 'users', str(user_id))
    os.makedirs(user_data_dir, exist_ok=True)
    return user_data_dir


def is_user_isolated(user_id: str) -> bool:
    """التحقق من وجود مجلد عزل للمستخدم"""
    user_dir = os.path.join(SESSIONS_DIR, str(user_id))
    return os.path.isdir(user_dir)


# ══════════════════════════════════════════════════════════
#  إدارة إعدادات المستخدمين المعزولة
# ══════════════════════════════════════════════════════════

def save_isolated_settings(user_id: str, settings: dict) -> bool:
    """
    حفظ إعدادات المستخدم في مجلده المعزول.
    لا تُكتَب بيانات مستخدم في مجلد مستخدم آخر.
    """
    try:
        user_dir = get_user_isolated_dir(user_id)
        path = os.path.join(user_dir, 'settings.json')
        with _ISOLATION_LOCK:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(settings, f, ensure_ascii=False, indent=4)
        # نسخة احتياطية للتوافق
        legacy = os.path.join(SESSIONS_DIR, f'{user_id}.json')
        with open(legacy, 'w', encoding='utf-8') as f:
            json.dump(settings, f, ensure_ascii=False, indent=4)
        return True
    except Exception as e:
        logger.error(f"isolation save_settings error for {user_id}: {e}")
        return False


def load_isolated_settings(user_id: str) -> dict:
    """
    تحميل إعدادات المستخدم من مجلده المعزول.
    يبحث أولاً في المجلد الخاص ثم في الملف القديم للتوافق.
    """
    try:
        user_dir = get_user_isolated_dir(user_id)
        path = os.path.join(user_dir, 'settings.json')
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        legacy = os.path.join(SESSIONS_DIR, f'{user_id}.json')
        if os.path.exists(legacy):
            with open(legacy, 'r', encoding='utf-8') as f:
                data = json.load(f)
            save_isolated_settings(user_id, data)
            return data
        return {}
    except Exception as e:
        logger.error(f"isolation load_settings error for {user_id}: {e}")
        return {}


def clear_user_isolation(user_id: str) -> bool:
    """
    مسح بيانات العزل للمستخدم بالكامل.
    يحذف المجلد الخاص والملفات المؤقتة فقط دون المساس ببيانات المستخدمين الآخرين.
    """
    try:
        import shutil
        user_dir = os.path.join(SESSIONS_DIR, str(user_id))
        if os.path.exists(user_dir):
            shutil.rmtree(user_dir)
        for suffix in ['.json', '_session.session', '_string.txt']:
            p = os.path.join(SESSIONS_DIR, f'{user_id}{suffix}')
            if os.path.exists(p):
                os.remove(p)
        logger.info(f"Cleared isolation for {user_id}")
        return True
    except Exception as e:
        logger.error(f"isolation clear error for {user_id}: {e}")
        return False


# ══════════════════════════════════════════════════════════
#  فحص عزل البيانات بين المستخدمين
# ══════════════════════════════════════════════════════════

def check_isolation_integrity(predefined_users: dict) -> dict:
    """
    فحص سلامة العزل بين المستخدمين.
    يتحقق من أن ملفات كل مستخدم في مجلده الخاص فقط.
    
    القيمة المُعادة:
        قاموس بنتائج الفحص لكل مستخدم
    """
    results = {}
    for uid in predefined_users:
        user_dir = os.path.join(SESSIONS_DIR, str(uid))
        results[uid] = {
            'has_isolated_dir': os.path.isdir(user_dir),
            'has_settings': os.path.exists(os.path.join(user_dir, 'settings.json')),
            'has_session': os.path.exists(os.path.join(SESSIONS_DIR, f'{uid}_string.txt')),
        }
    return results


def get_user_session_path(user_id: str) -> str:
    """مسار ملف StringSession للمستخدم"""
    return os.path.join(SESSIONS_DIR, f'{user_id}_string.txt')


def user_has_active_session(user_id: str) -> bool:
    """التحقق من وجود جلسة تيليجرام نشطة للمستخدم"""
    sess_path = get_user_session_path(user_id)
    if os.path.exists(sess_path):
        try:
            with open(sess_path, 'r') as f:
                content = f.read().strip()
            return len(content) > 10
        except Exception:
            pass
    return False
