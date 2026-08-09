"""
card_system.py
══════════════════════════════════════════════════════════════
نظام بطاقات الشحن والقسائم — منفصل كوحدة مستقلة
مرتبط بـ app.py عبر الاستيراد
══════════════════════════════════════════════════════════════
"""

import os
import json
import time
import secrets
import hashlib
import threading
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

DATA_DIR   = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(DATA_DIR, exist_ok=True)

CARDS_FILE = os.path.join(DATA_DIR, "cards.json")
_CARDS_LOCK = threading.Lock()

# ══════════════════════════════════════════════════════════
#  دوال البيانات الأساسية
# ══════════════════════════════════════════════════════════

try:
    import github_db as _ghdb
    _GH_CARDS_PATH = "data/cards.json"
except ImportError:
    _ghdb = None
    _GH_CARDS_PATH = None

_CARDS_DEFAULT = {
    "card_system_enabled": False,
    "plans": [
        {"id": 1, "name": "يومية",   "time_limit": 86400,   "data_limit": 5368709120,  "profile_name": "daily"},
        {"id": 2, "name": "أسبوعية", "time_limit": 604800,  "data_limit": 10737418240, "profile_name": "weekly"},
        {"id": 3, "name": "شهرية",   "time_limit": 2592000, "data_limit": 32212254720, "profile_name": "monthly"},
        {"id": 4, "name": "دائمة",   "time_limit": 0,       "data_limit": 0,           "profile_name": "unlimited"}
    ],
    "vouchers": [],
    "active_card_sessions": []
}

def load_cards_data():
    """تحميل بيانات البطاقات — GitHub أولاً ثم المحلي ثم الافتراضي"""
    if _ghdb:
        data = _ghdb.gh_load(_GH_CARDS_PATH, CARDS_FILE, None)
        if data is not None:
            # تأكد من وجود المفاتيح الأساسية
            for k, v in _CARDS_DEFAULT.items():
                if k not in data:
                    data[k] = v
            return data
    # سقط محلي كلاسيكي
    with _CARDS_LOCK:
        try:
            if os.path.exists(CARDS_FILE):
                with open(CARDS_FILE, 'r', encoding='utf-8') as f:
                    d = json.load(f)
                for k, v in _CARDS_DEFAULT.items():
                    if k not in d:
                        d[k] = v
                return d
        except Exception:
            pass
        default = dict(_CARDS_DEFAULT)
        try:
            with open(CARDS_FILE, 'w', encoding='utf-8') as f:
                json.dump(default, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
        return default


def save_cards_data(data):
    """حفظ بيانات البطاقات محلياً + رفع إلى GitHub"""
    if _ghdb:
        _ghdb.gh_save(_GH_CARDS_PATH, CARDS_FILE, data, "تحديث بيانات البطاقات")
        return
    with _CARDS_LOCK:
        try:
            with open(CARDS_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Error saving cards data: {e}")


def voucher_display_code(v):
    """يرجع رمز البطاقة الظاهر للمشرف — يدعم الكروت القديمة التي لا تحتوي على 'code'."""
    return v.get("code") or (v.get("code_hash", "")[:12] + "***" if v.get("code_hash") else "—")


def voucher_display_plan_name(v, plans=None):
    """يرجع اسم الخطة — يدعم الكروت القديمة التي تخزن plan_id فقط بدون plan_name."""
    if v.get("plan_name"):
        return v["plan_name"]
    if plans is None:
        plans = load_cards_data().get("plans", [])
    plan = next((p for p in plans if p.get("id") == v.get("plan_id")), None)
    return plan["name"] if plan else "بدون خطة"


def generate_vouchers(plan_id, count=10, allowed_features=None):
    """إنشاء قسائم بطاقات جديدة — كل كرت من 9 أرقام فقط"""
    import random
    data = load_cards_data()
    plan = next((p for p in data["plans"] if p["id"] == plan_id), None)
    if not plan:
        raise ValueError("الخطة غير موجودة")
    if allowed_features is None:
        allowed_features = []
    # جمع الأكواد الموجودة لضمان عدم التكرار
    existing_codes = {v.get("code") for v in data["vouchers"] if v.get("code")}
    codes = []
    for _ in range(count):
        # توليد كود من 9 أرقام عشوائية فريد
        attempts = 0
        while attempts < 10000:
            code = str(random.randint(100000000, 999999999))
            if code not in existing_codes:
                break
            attempts += 1
        existing_codes.add(code)
        hashed = hashlib.sha256(code.encode()).hexdigest()
        data["vouchers"].append({
            "code": code,
            "code_hash": hashed,
            "plan_id": plan_id,
            "plan_name": plan["name"],
            "allowed_features": allowed_features,
            "status": "unused",
            "created_at": datetime.now().isoformat(),
            "used_at": None,
            "expires_at": None
        })
        codes.append(code)
    save_cards_data(data)
    return codes


def validate_voucher(code):
    """التحقق من صحة قسيمة البطاقة — يدعم الكروت الجديدة (9 أرقام) والقديمة (Hex)"""
    stripped = code.strip()
    # محاولة التحقق كـ 9 أرقام أولاً
    normalized = stripped
    hashed = hashlib.sha256(normalized.encode()).hexdigest()
    data = load_cards_data()
    voucher = next((v for v in data["vouchers"] if v["code_hash"] == hashed), None)
    if not voucher:
        return None, "❌ الرمز غير صحيح"
    if voucher["status"] == "used":
        return None, "❌ تم استخدام هذا الرمز مسبقاً"
    if voucher["status"] == "expired":
        return None, "❌ انتهت صلاحية الرمز"
    plan = next((p for p in data["plans"] if p["id"] == voucher["plan_id"]), None)
    if not plan:
        return None, "❌ الخطة غير موجودة"
    return {"voucher": voucher, "plan": plan}, None


def activate_card_voucher(code, client_ip="0.0.0.0"):
    """تفعيل قسيمة بطاقة وإنشاء جلسة نشطة"""
    result, err = validate_voucher(code)
    if err:
        return {"success": False, "message": err}
    voucher = result["voucher"]
    plan = result["plan"]
    data = load_cards_data()

    # تحديث حالة القسيمة (يدعم الصيغتين: 9 أرقام والقديمة Hex)
    # نستخدم code_hash المحفوظ في voucher مباشرةً بدلاً من إعادة الحساب
    target_hash = voucher.get("code_hash", "")
    for v in data["vouchers"]:
        if v.get("code_hash") == target_hash:
            v["status"] = "used"
            v["used_at"] = datetime.now().isoformat()
            break

    # إنشاء جلسة نشطة
    new_session = {
        "session_id": secrets.token_urlsafe(16),
        "plan_id": plan["id"],
        "plan_name": plan["name"],
        "allowed_features": voucher.get("allowed_features", []),
        "created_at": datetime.now().isoformat(),
        "expires_at": (datetime.now().timestamp() + plan["time_limit"]),
        "client_ip": client_ip,
    }
    data.setdefault("active_card_sessions", []).append(new_session)
    save_cards_data(data)
    return {"success": True, "session": new_session, "plan": plan}


def terminate_card_session(session_id, reason="انتهت الجلسة"):
    """إنهاء جلسة بطاقة نشطة"""
    data = load_cards_data()
    s = next((x for x in data.get("active_card_sessions", []) if x.get("session_id") == session_id), None)
    if s:
        logger.info(f"Terminating card session {session_id}: {reason}")
        data["active_card_sessions"] = [x for x in data["active_card_sessions"] if x["session_id"] != session_id]
        save_cards_data(data)


def start_card_session_monitor(socketio_obj=None):
    """بدء مراقبة انتهاء صلاحية جلسات البطاقات في الخلفية"""
    def _monitor():
        while True:
            try:
                time.sleep(60)
                data = load_cards_data()
                now = datetime.now().timestamp()
                for s in list(data.get("active_card_sessions", [])):
                    expires_at = s.get("expires_at", 0)
                    sid = s.get("session_id")
                    if expires_at and now > expires_at:
                        terminate_card_session(sid, "انتهى الوقت تلقائياً")
                        if socketio_obj:
                            try:
                                socketio_obj.emit('card_session_expired', {"session_id": sid})
                            except Exception:
                                pass
            except Exception as e:
                logger.error(f"card_session_monitor: {e}")

    t = threading.Thread(target=_monitor, daemon=True)
    t.start()
    return t
