# -*- coding: utf-8 -*-
"""
وحدة المزامنة مع قاعدة البيانات الخارجية Firestore والكاش المحلي
==============================================================
تدعم حفظ واسترجاع:
1. أرقام الهواتف المحفوظة
2. الروابط المكتشفة والمحفوظة (واتساب وتيليجرام)
3. تقارير فحص ومستوى أمان المجموعات (Group Safety Reports)
مع ميزة المزامنة الخلفية غير الحاجزة (Non-blocking background sync)
والكاش المحلي الفوري لتسريع الأداء وتفادي تجميد الخادم.
"""

import json
import logging
import os
import re
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger('firestore_sync')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
BRIDGE_SCRIPT = os.path.join(BASE_DIR, 'firestore_bridge.js')

LOCAL_SAFETY_CACHE_FILE = os.path.join(DATA_DIR, 'group_safety_cache.json')
LOCAL_LINKS_CACHE_FILE = os.path.join(DATA_DIR, 'saved_links.json')
LOCAL_PHONES_CACHE_FILE = os.path.join(DATA_DIR, 'saved_phones.json')

_SAFETY_CACHE_LOCK = threading.Lock()
_LINKS_CACHE_LOCK = threading.Lock()
_PHONES_CACHE_LOCK = threading.Lock()

# مجمع خيوط للمزامنة الخلفية غير الحاجزة مع Firestore
_SYNC_EXECUTOR = ThreadPoolExecutor(max_workers=3, thread_name_prefix="FirestoreSyncWorker")

_SYNC_STATS = {
    "total_synced_reports": 0,
    "total_synced_links": 0,
    "last_sync_time": None,
    "last_error": None,
    "is_online": True
}


def _load_json_file(file_path, default_val):
    try:
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        logger.debug(f"خطأ في قراءة الكاش {file_path}: {e}")
    return default_val


def _save_json_file(file_path, data):
    try:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.error(f"خطأ في حفظ الكاش {file_path}: {e}")
        return False


# ==========================================
# 📱 أرقام الهواتف (Phone Numbers)
# ==========================================
DEFAULT_PHONE_NUMBERS = [
    {"phone_number": "+573244867204", "is_default": True, "label": "رقم أساسي"},
    {"phone_number": "+201221349790", "is_default": True, "label": "رقم أساسي"},
    {"phone_number": "+201148863243", "is_default": True, "label": "رقم أساسي"},
    {"phone_number": "+213797500921", "is_default": True, "label": "رقم أساسي"},
    {"phone_number": "+201274386864", "is_default": True, "label": "رقم أساسي"},
    {"phone_number": "+201120945094", "is_default": True, "label": "رقم أساسي"},
    {"phone_number": "+966539709737", "is_default": True, "label": "رقم أساسي"}
]


def get_saved_phone_numbers():
    """استرجاع أرقام الهواتف المحفوظة مع Fallback للكاش المحلي"""
    with _PHONES_CACHE_LOCK:
        cached = _load_json_file(LOCAL_PHONES_CACHE_FILE, [])

    try:
        proc = subprocess.run(
            ['node', BRIDGE_SCRIPT, 'get_phones'],
            capture_output=True, text=True, timeout=8, cwd=BASE_DIR
        )
        if proc.returncode == 0:
            res = json.loads(proc.stdout.strip())
            if res.get('success'):
                phones = res.get('phones', [])
                if phones:
                    with _PHONES_CACHE_LOCK:
                        _save_json_file(LOCAL_PHONES_CACHE_FILE, phones)
                    return phones
    except Exception as e:
        logger.warning(f"تعذر جلب الأرقام من Firestore مباشرة ({e})، استخدام الكاش المحلي")

    return cached if cached else list(DEFAULT_PHONE_NUMBERS)


def save_phone_number(phone, label='رقم محفوظ'):
    """حفظ رقم هاتف جديد في الكاش المحلي وخلفياً في Firestore"""
    if not phone:
        return None
    clean_phone = str(phone).strip()
    new_entry = {
        "phone_number": clean_phone,
        "is_default": False,
        "label": label,
        "added_at": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    }

    with _PHONES_CACHE_LOCK:
        phones = _load_json_file(LOCAL_PHONES_CACHE_FILE, list(DEFAULT_PHONE_NUMBERS))
        if not any(p.get('phone_number') == clean_phone for p in phones):
            phones.append(new_entry)
            _save_json_file(LOCAL_PHONES_CACHE_FILE, phones)

    # حفظ في Firestore عبر خيط خلفي
    def _bg_save():
        try:
            proc = subprocess.run(
                ['node', BRIDGE_SCRIPT, 'add_phone', clean_phone],
                capture_output=True, text=True, timeout=10, cwd=BASE_DIR
            )
            if proc.returncode == 0:
                logger.info(f"✅ تم حفظ الرقم {clean_phone} في Firestore")
        except Exception as e:
            logger.warning(f"فشل حفظ الرقم في Firestore: {e}")

    _SYNC_EXECUTOR.submit(_bg_save)
    return new_entry


# ==========================================
# 🔗 الروابط المحفوظة (Saved Links)
# ==========================================
def get_firestore_links():
    """استرجاع كل الروابط المحفوظة مع الكاش المحلي الفوري"""
    with _LINKS_CACHE_LOCK:
        cached_links = _load_json_file(LOCAL_LINKS_CACHE_FILE, [])

    try:
        proc = subprocess.run(
            ['node', BRIDGE_SCRIPT, 'get_links'],
            capture_output=True, text=True, timeout=8, cwd=BASE_DIR
        )
        if proc.returncode == 0:
            res = json.loads(proc.stdout.strip())
            if res.get('success'):
                cloud_links = res.get('links', [])
                if cloud_links:
                    with _LINKS_CACHE_LOCK:
                        _save_json_file(LOCAL_LINKS_CACHE_FILE, cloud_links)
                    return cloud_links
    except Exception as e:
        logger.warning(f"تعذر جلب الروابط من Firestore ({e})، استخدام الكاش المحلي")

    return cached_links


def add_firestore_link(link_dict):
    """
    حفظ رابط فورياً في الكاش المحلي ومزامنته في الخلفية مع Firestore
    لتفادي حجب معالجة الرسائل ورادار الروابط.
    """
    if not link_dict or not link_dict.get('url'):
        return None

    url = link_dict.get('url')
    # 1. حفظ محلي فوري
    with _LINKS_CACHE_LOCK:
        links = _load_json_file(LOCAL_LINKS_CACHE_FILE, [])
        # منع تكرار نفس الرابط في الكاش المحلي
        existing = next((l for l in links if l.get('url') == url), None)
        if not existing:
            links.insert(0, link_dict)
            if len(links) > 2000:
                links = links[:2000]
            _save_json_file(LOCAL_LINKS_CACHE_FILE, links)

    # 2. مزامنة غير حاجزة مع Firestore
    def _bg_add_link():
        try:
            payload = json.dumps(link_dict, ensure_ascii=False)
            proc = subprocess.run(
                ['node', BRIDGE_SCRIPT, 'add_link', payload],
                capture_output=True, text=True, timeout=12, cwd=BASE_DIR
            )
            if proc.returncode == 0:
                _SYNC_STATS["total_synced_links"] += 1
                _SYNC_STATS["last_sync_time"] = time.strftime('%Y-%m-%d %H:%M:%S')
                logger.debug(f"✅ تم حفظ الرابط في Firestore: {url}")
        except Exception as e:
            _SYNC_STATS["last_error"] = str(e)
            logger.warning(f"تنبيه مزامنة رابط مع Firestore: {e}")

    _SYNC_EXECUTOR.submit(_bg_add_link)
    return link_dict


def delete_firestore_link(link_id):
    """حذف رابط من الكاش المحلي وFirestore"""
    if not link_id:
        return False

    with _LINKS_CACHE_LOCK:
        links = _load_json_file(LOCAL_LINKS_CACHE_FILE, [])
        links = [l for l in links if str(l.get('id', '')) != str(link_id)]
        _save_json_file(LOCAL_LINKS_CACHE_FILE, links)

    def _bg_del():
        try:
            subprocess.run(
                ['node', BRIDGE_SCRIPT, 'delete_link', str(link_id)],
                capture_output=True, text=True, timeout=10, cwd=BASE_DIR
            )
        except Exception as e:
            logger.warning(f"فشل حذف الرابط من Firestore: {e}")

    _SYNC_EXECUTOR.submit(_bg_del)
    return True


# ==========================================
# 🛡️ تقارير فحص وأمان المجموعات (Group Safety Reports)
# ==========================================
def _normalize_group_key(k):
    if not k:
        return ""
    clean = str(k).strip().lower()
    return re.sub(r'^(?:https?://)?(?:t\.me|telegram\.me)/', '', clean).lstrip('@')


def get_group_safety_report_from_db(group_key, alt_key=None):
    """
    استرجاع تقرير فحص المجموعة من الكاش المحلي أولاً (بسرعة فائقة)
    وإذا لم يتوفر، استرجاعه من Firestore وحفظه محلياً.
    """
    if not group_key and not alt_key:
        return None

    keys_to_check = [k for k in [group_key, alt_key] if k]

    # 1. فحص الكاش المحلي أولاً
    with _SAFETY_CACHE_LOCK:
        local_cache = _load_json_file(LOCAL_SAFETY_CACHE_FILE, {})
        for k in keys_to_check:
            clean_k = str(k).strip().lower()
            if clean_k in local_cache:
                return local_cache[clean_k]
            norm_k = _normalize_group_key(clean_k)
            if norm_k in local_cache:
                return local_cache[norm_k]

    # 2. الاسترجاع من Firestore
    for k in keys_to_check:
        try:
            proc = subprocess.run(
                ['node', BRIDGE_SCRIPT, 'get_group_report', str(k).strip()],
                capture_output=True, text=True, timeout=8, cwd=BASE_DIR
            )
            if proc.returncode == 0:
                res = json.loads(proc.stdout.strip())
                if res.get('success') and res.get('report'):
                    report = res['report']
                    with _SAFETY_CACHE_LOCK:
                        local_cache = _load_json_file(LOCAL_SAFETY_CACHE_FILE, {})
                        local_cache[str(k).strip().lower()] = report
                        norm = _normalize_group_key(k)
                        if norm:
                            local_cache[norm] = report
                        if alt_key:
                            local_cache[str(alt_key).strip().lower()] = report
                        _save_json_file(LOCAL_SAFETY_CACHE_FILE, local_cache)
                    return report
        except Exception as e:
            logger.warning(f"خطأ استرجاع تقرير المجموعة من Firestore لـ {k}: {e}")

    return None


def save_group_safety_report_to_db(report_dict):
    """
    حفظ دائم وثابت لتقرير المجموعة:
    1. حفظ فوري في الكاش المحلي (بدون تأخير لحلقة الإرسال).
    2. مزامنة غير حاجزة في خيط خلفي مع Firestore.
    """
    if not report_dict:
        return None

    key = report_dict.get('group_key') or report_dict.get('group_id') or report_dict.get('group_title')
    if not key:
        return None

    # 1. حفظ محلي فوري
    with _SAFETY_CACHE_LOCK:
        local_cache = _load_json_file(LOCAL_SAFETY_CACHE_FILE, {})
        str_key = str(key).strip().lower()
        local_cache[str_key] = report_dict
        norm = _normalize_group_key(str_key)
        if norm:
            local_cache[norm] = report_dict
        if report_dict.get('group_id'):
            local_cache[str(report_dict['group_id']).strip().lower()] = report_dict
        if report_dict.get('username'):
            local_cache[str(report_dict['username']).strip().lower()] = report_dict
        _save_json_file(LOCAL_SAFETY_CACHE_FILE, local_cache)

    # 2. مزامنة غير حاجزة مع Firestore
    def _bg_save_report():
        try:
            payload = json.dumps(report_dict, ensure_ascii=False)
            proc = subprocess.run(
                ['node', BRIDGE_SCRIPT, 'save_group_report', payload],
                capture_output=True, text=True, timeout=12, cwd=BASE_DIR
            )
            if proc.returncode == 0:
                _SYNC_STATS["total_synced_reports"] += 1
                _SYNC_STATS["last_sync_time"] = time.strftime('%Y-%m-%d %H:%M:%S')
                logger.info(f"✅ تم حفظ تقرير المجموعة في Firestore: {key}")
        except Exception as e:
            _SYNC_STATS["last_error"] = str(e)
            logger.warning(f"تنبيه حفظ تقرير المجموعة في Firestore: {e}")

    _SYNC_EXECUTOR.submit(_bg_save_report)
    return report_dict


def get_sync_status():
    """معلومات حالة المزامنة والكاش لخدمة الفحص والمراقبة"""
    with _SAFETY_CACHE_LOCK:
        cached_reports_count = len(_load_json_file(LOCAL_SAFETY_CACHE_FILE, {}))
    with _LINKS_CACHE_LOCK:
        cached_links_count = len(_load_json_file(LOCAL_LINKS_CACHE_FILE, []))

    return {
        "success": True,
        "online": _SYNC_STATS["is_online"],
        "cached_reports": cached_reports_count,
        "cached_links": cached_links_count,
        "synced_reports": _SYNC_STATS["total_synced_reports"],
        "synced_links": _SYNC_STATS["total_synced_links"],
        "last_sync_time": _SYNC_STATS["last_sync_time"],
        "last_error": _SYNC_STATS["last_error"]
    }
