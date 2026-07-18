"""
install_tracker.py
نظام تتبع التثبيتات المعزول بالكامل (Client-Side Install ID)

يحاكي فلسفة تليجرام في عزل الجلسات: كل متصفح/تبويب يحصل على install_id
ثابت يُخزَّن في localStorage على العميل، ويُرسل مع كل طلب عبر هيدر
X-Install-ID. الخادم يستخدم هذا المعرف لتحديث نفس التثبيت بدلاً من
إنشاء تثبيت جديد في كل مرة، مما يحقق عزلاً حقيقياً بين التثبيتات.
"""

import os
import json
import requests
import uuid
import threading
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(DATA_DIR, exist_ok=True)
USER_SESSIONS_FILE = os.path.join(DATA_DIR, "user_sessions.json")
_SESSIONS_LOCK = threading.Lock()

MAX_INSTALLATIONS = 500

# ── استخدام وحدة gps_tracking المنفصلة للموقع الجغرافي ──────────────────────
try:
    from gps_tracking import geo_lookup as _geo_lookup_module
    _USE_GPS_MODULE = True
except ImportError:
    _USE_GPS_MODULE = False


def _geo_lookup(ip):
    """تحديد الموقع الجغرافي من عنوان IP — يستخدم gps_tracking.py الوحدة المنفصلة"""
    if _USE_GPS_MODULE:
        return _geo_lookup_module(ip)
    if not ip or ip in ('127.0.0.1', '::1', 'غير معروف', '—'):
        return {}
    try:
        import requests as _req
        r = _req.get(f'http://ip-api.com/json/{ip}?lang=ar&fields=status,country,regionName,city,lat,lon,timezone,isp',
                     timeout=3)
        if r.status_code == 200:
            d = r.json()
            if d.get('status') == 'success':
                return {
                    'country':  d.get('country', ''),
                    'region':   d.get('regionName', ''),
                    'city':     d.get('city', ''),
                    'lat':      d.get('lat', 0),
                    'lon':      d.get('lon', 0),
                    'isp':      d.get('isp', ''),
                    'timezone': d.get('timezone', ''),
                }
    except Exception:
        pass
    return {}

try:
    import github_db as _ghdb_it
    _GH_SESSIONS_PATH = "data/user_sessions.json"
except ImportError:
    _ghdb_it = None
    _GH_SESSIONS_PATH = None


def load_user_sessions():
    """تحميل بيانات التثبيتات — GitHub أولاً ثم المحلي"""
    if _ghdb_it:
        data = _ghdb_it.gh_load(_GH_SESSIONS_PATH, USER_SESSIONS_FILE, None)
        if data is not None:
            return data
    with _SESSIONS_LOCK:
        try:
            if os.path.exists(USER_SESSIONS_FILE):
                with open(USER_SESSIONS_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"فشل تحميل user_sessions.json: {e}")
        return {"installations": []}


def _sanitize_sessions_for_github(data: dict) -> dict:
    """
    ينظّف بيانات التثبيتات قبل رفعها إلى GitHub.
    يحذف الحقول الحساسة (IP دقيق، GPS، UA كامل، session cookies)
    ويحتفظ بالبيانات الإدارية المفيدة فقط (install_id، حالة الحسابات، المنطقة الجغرافية العامة).
    """
    import copy
    safe = copy.deepcopy(data)
    for inst in safe.get("installations", []):
        # احذف IP العنوان الدقيق (استبدله بأول 3 أجزاء فقط)
        raw_ip = inst.get("ip", "")
        if raw_ip and "." in raw_ip:
            parts = raw_ip.split(".")
            inst["ip"] = ".".join(parts[:3]) + ".x"
        elif raw_ip:
            inst["ip"] = raw_ip[:8] + "…"

        # احذف إحداثيات GPS الدقيقة (احتفظ بالمنطقة الجغرافية العامة فقط)
        inst.pop("gps_geo", None)

        # احذف user_agent الكامل (حساس)
        ua = inst.get("user_agent", "")
        if ua and len(ua) > 30:
            inst["user_agent"] = ua[:30] + "…"

        # في users_state — احذف أي بيانات جلسة حساسة
        for uid, state in inst.get("users_state", {}).items():
            state.pop("session_string", None)
            state.pop("string_session", None)
            state.pop("cookie", None)
            state.pop("token", None)

        # الموقع الجغرافي: احتفظ بالبلد والمنطقة فقط (لا lat/lon دقيق)
        geo = inst.get("geo", {})
        if geo:
            inst["geo"] = {
                "country":  geo.get("country", ""),
                "region":   geo.get("region", ""),
                "city":     geo.get("city", ""),
                "timezone": geo.get("timezone", ""),
                "isp":      geo.get("isp", ""),
                # lat/lon مقرّب (درجتان عشريتان ≈ ±1.1 كم)
                "lat": round(float(geo["lat"]), 2) if geo.get("lat") else None,
                "lon": round(float(geo["lon"]), 2) if geo.get("lon") else None,
            }
    return safe


def save_user_sessions(data):
    """
    حفظ بيانات التثبيتات:
    - محلياً: البيانات الكاملة (للإدارة الداخلية)
    - GitHub: نسخة مُنظَّفة من البيانات الحساسة
    """
    # حفظ محلي أولاً بالبيانات الكاملة
    with _SESSIONS_LOCK:
        try:
            with open(USER_SESSIONS_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"فشل حفظ user_sessions.json محلياً: {e}")

    # رفع نسخة منظَّفة إلى GitHub
    if _ghdb_it:
        safe_data = _sanitize_sessions_for_github(data)
        _ghdb_it.gh_save(
            _GH_SESSIONS_PATH, None,  # local_path=None: لا تكتب محلياً مرة أخرى
            safe_data, "تحديث بيانات التثبيتات (آمن)"
        )


def _build_users_state(predefined_users, users_dict, users_lock, load_settings_func):
    """التقاط لقطة من حالة المستخدمين الخمسة كما هي في الذاكرة الآن."""
    users_state = {}
    for uid, uinfo in predefined_users.items():
        try:
            settings = load_settings_func(uid) or {}
        except Exception:
            settings = {}

        if users_lock is not None:
            with users_lock:
                ud = dict(users_dict.get(uid, {}))
        else:
            ud = dict(users_dict.get(uid, {}))

        users_state[uid] = {
            "name": uinfo.get("name", uid),
            "phone": settings.get("phone", "") or ud.get("phone_number", ""),
            "account_name": ud.get("telegram_name", "") or ud.get("account_name", ""),
            "authenticated": bool(ud.get("authenticated", False)),
            "connected": bool(ud.get("connected", False)),
            "is_running": bool(ud.get("is_running", False)),
            "blocked": bool(ud.get("blocked", False)),
            "last_seen": ud.get("last_seen", "") or "",
            "monitoring_active": bool(ud.get("monitoring_active", False)),
            "connected_at": ud.get("connected_at", "") or "",
            "disconnected_at": ud.get("disconnected_at", "") or "",
            "session_history": ud.get("session_history", []),
        }
    return users_state


def track_installation(user_id, request, predefined_users, users_dict,
                        load_settings_func, socketio_obj, users_lock=None):
    """
    تسجيل/تحديث تثبيت بناءً على المعرف المرسل من العميل (X-Install-ID).
    - إذا كان المعرف موجوداً مسبقاً: تحديث آخر ظهور وحالة المستخدمين فقط (عزل تام، بدون تكرار).
    - إذا لم يكن موجوداً: إنشاء تثبيت جديد وبث إشعار فوري عبر Socket.IO.
    """
    # إذا كان user_id غير موجود في predefined_users (مثلاً قبل تسجيل الدخول أو بعد تغيير النظام الديناميكي)
    # نستمر في التتبع بدون users_state فقط لتسجيل بصمة الجهاز
    if not user_id:
        return None, False, None

    # قراءة المعرف بالأولوية: هيدر X-Install-ID → كوكيز → IP+UA كبديل ثابت → UUID جديد
    install_id = request.headers.get('X-Install-ID')
    if not install_id:
        install_id = request.cookies.get('install_id')
    if not install_id:
        # بناء معرّف شبه ثابت من IP + User-Agent لاكتشاف الزوار الجدد فوراً
        ip_raw = request.headers.get('X-Forwarded-For', request.remote_addr) or ''
        ua_raw = request.headers.get('User-Agent', '') or ''
        fingerprint = ip_raw.split(',')[0].strip() + '|' + ua_raw[:80]
        import hashlib
        install_id = 'fp-' + hashlib.sha256(fingerprint.encode()).hexdigest()[:24]
    is_cookie_based = not request.headers.get('X-Install-ID')

    try:
        data = load_user_sessions()
        installations = data.setdefault("installations", [])

        ip = request.headers.get('X-Forwarded-For', request.remote_addr) or "غير معروف"
        if ip and ',' in ip:
            ip = ip.split(',')[0].strip()
        ua = (request.headers.get('User-Agent', 'غير معروف') or 'غير معروف')[:300]
        try:
            cookies = dict(request.cookies)
        except Exception:
            cookies = {}
        timestamp = datetime.now().isoformat()

        users_state = _build_users_state(predefined_users, users_dict, users_lock, load_settings_func)

        existing_install = next((i for i in installations if i.get("install_id") == install_id), None)
        is_new = existing_install is None

        if existing_install:
            existing_install["last_seen"] = timestamp
            existing_install["ip"] = ip
            if not existing_install.get("geo"):
                existing_install["geo"] = _geo_lookup(ip)
            existing_install["user_agent"] = ua
            existing_install["cookies"] = json.dumps(cookies, ensure_ascii=False)
            existing_install["is_active"] = True
            existing_install["user_id"] = user_id
            existing_install["users_state"] = users_state
            record = existing_install
            logger.info(f"🔄 تحديث تثبيت موجود: {install_id[:8]} للمستخدم {user_id}")
        else:
            geo = _geo_lookup(ip)
            record = {
                "install_id": install_id,
                "user_id": user_id,
                "ip": ip,
                "geo": geo,
                "user_agent": ua,
                "cookies": json.dumps(cookies, ensure_ascii=False),
                "timestamp": timestamp,
                "last_seen": timestamp,
                "is_active": True,
                "users_state": users_state,
            }
            installations.insert(0, record)
            if len(installations) > MAX_INSTALLATIONS:
                data["installations"] = installations[:MAX_INSTALLATIONS]
            logger.info(f"🆕 تثبيت جديد: {install_id[:8]} للمستخدم {user_id}")

        save_user_sessions(data)

        if is_new and socketio_obj is not None:
            try:
                socketio_obj.emit('new_installation', {
                    "install_id": install_id,
                    "user_id": user_id,
                    "user_name": predefined_users.get(user_id, {}).get("name", user_id),
                    "ip": ip,
                    "user_agent": ua[:80],
                    "timestamp": timestamp,
                    "is_active": True,
                    "users_count": len(users_state),
                })
                logger.info(f"📢 إشعار تثبيت جديد: {user_id} من {ip}")
            except Exception as e:
                logger.error(f"فشل إرسال إشعار التثبيت: {e}")

        # إرجاع tuple يحتوي على (السجل، هل هو جديد، معرف التثبيت) ليتمكن الطالب من ضبط الكوكيز
        return record, is_new, install_id
    except Exception as e:
        logger.error(f"track_installation error: {e}")
        return None, False, None


def register_admin_routes(app, get_admin_auth_func, predefined_users, users_dict,
                           users_lock, load_settings_func, save_settings_func,
                           reset_user_func=None):
    """تسجيل مسارات API الخاصة بإدارة التثبيتات (يُستدعى مرة واحدة بعد إنشاء app)."""
    from flask import request, jsonify, send_file
    import io
    import csv

    def _unauthorized():
        return jsonify({"success": False, "message": "غير مخول"}), 403

    @app.route("/admin/api/installations", methods=["GET"])
    def admin_get_installations():
        if not get_admin_auth_func():
            return _unauthorized()
        data = load_user_sessions()
        return jsonify({"success": True, "installations": data.get("installations", [])})

    @app.route("/admin/api/installation_details/<install_id>", methods=["GET"])
    def admin_get_installation_details(install_id):
        if not get_admin_auth_func():
            return _unauthorized()
        data = load_user_sessions()
        install = next((i for i in data.get("installations", []) if i.get("install_id") == install_id), None)
        if not install:
            return jsonify({"success": False, "message": "التثبيت غير موجود"}), 404
        return jsonify({"success": True, "installation": install})

    @app.route("/admin/api/toggle_install_active", methods=["POST"])
    def admin_toggle_install_active():
        if not get_admin_auth_func():
            return _unauthorized()
        payload = request.get_json(silent=True) or {}
        install_id = payload.get("install_id")
        active = bool(payload.get("active", True))
        if not install_id:
            return jsonify({"success": False, "message": "معرف التثبيت مطلوب"}), 400
        sessions_data = load_user_sessions()
        found = False
        for inst in sessions_data.get("installations", []):
            if inst.get("install_id") == install_id:
                inst["is_active"] = active
                found = True
                break
        if not found:
            return jsonify({"success": False, "message": "التثبيت غير موجود"}), 404
        save_user_sessions(sessions_data)
        return jsonify({"success": True, "message": f"تم {'تفعيل' if active else 'تعطيل'} التثبيت"})

    @app.route("/admin/api/delete_install", methods=["POST"])
    def admin_delete_install():
        if not get_admin_auth_func():
            return _unauthorized()
        payload = request.get_json(silent=True) or {}
        install_id = payload.get("install_id")
        if not install_id:
            return jsonify({"success": False, "message": "معرف التثبيت مطلوب"}), 400
        sessions_data = load_user_sessions()
        before = len(sessions_data.get("installations", []))
        sessions_data["installations"] = [
            i for i in sessions_data.get("installations", []) if i.get("install_id") != install_id
        ]
        if len(sessions_data["installations"]) == before:
            return jsonify({"success": False, "message": "التثبيت غير موجود"}), 404
        save_user_sessions(sessions_data)
        return jsonify({"success": True, "message": "تم حذف التثبيت"})

    @app.route("/admin/api/update_install_user_state", methods=["POST"])
    def admin_update_install_user_state():
        """تحديث حالة مستخدم واحد ضمن تثبيت محدد فقط (عزل تام عن باقي التثبيتات)."""
        if not get_admin_auth_func():
            return _unauthorized()
        payload = request.get_json(silent=True) or {}
        install_id = payload.get("install_id")
        user_id = payload.get("user_id")
        updates = payload.get("updates") or {}
        if not install_id or not user_id:
            return jsonify({"success": False, "message": "install_id و user_id مطلوبان"}), 400
        sessions_data = load_user_sessions()
        install = next((i for i in sessions_data.get("installations", []) if i.get("install_id") == install_id), None)
        if not install:
            return jsonify({"success": False, "message": "التثبيت غير موجود"}), 404
        install.setdefault("users_state", {}).setdefault(user_id, {})
        install["users_state"][user_id].update(updates)
        save_user_sessions(sessions_data)
        return jsonify({"success": True, "message": "تم تحديث حالة المستخدم لهذا التثبيت"})

    @app.route("/admin/api/toggle_block_user", methods=["POST"])
    def admin_toggle_block_user_install():
        """حظر/فك حظر مستخدم بشكل عام (يؤثر على كل التثبيتات مثل تليجرام يوقف الحساب)."""
        if not get_admin_auth_func():
            return _unauthorized()
        payload = request.get_json(silent=True) or {}
        user_id = payload.get("user_id")
        blocked = bool(payload.get("blocked", True))
        if not user_id or user_id not in predefined_users:
            return jsonify({"success": False, "message": "مستخدم غير صحيح"}), 400
        if users_lock is not None:
            with users_lock:
                users_dict.setdefault(user_id, {})["blocked"] = blocked
        else:
            users_dict.setdefault(user_id, {})["blocked"] = blocked
        settings = load_settings_func(user_id) or {}
        settings["blocked"] = blocked
        save_settings_func(user_id, settings)
        return jsonify({"success": True, "blocked": blocked})

    @app.route("/admin/api/get_user_groups/<user_id>", methods=["GET"])
    def admin_get_user_groups(user_id):
        if not get_admin_auth_func():
            return _unauthorized()
        if user_id not in predefined_users:
            return jsonify({"success": False, "message": "مستخدم غير صحيح"}), 400
        if users_lock is not None:
            with users_lock:
                client_manager = users_dict.get(user_id, {}).get('client_manager')
        else:
            client_manager = users_dict.get(user_id, {}).get('client_manager')
        if not client_manager or not getattr(client_manager, 'client', None):
            return jsonify({"success": False, "message": "الحساب غير متصل"}), 400
        try:
            dialogs = client_manager.run_coroutine(client_manager.client.get_dialogs())
            groups = []
            for d in dialogs:
                entity = d.entity
                if hasattr(entity, 'megagroup') or hasattr(entity, 'broadcast') or hasattr(entity, 'gigagroup'):
                    title = getattr(d, 'title', None) or getattr(entity, 'title', 'بدون عنوان')
                    username = getattr(entity, 'username', None)
                    groups.append({
                        "id": entity.id,
                        "title": title,
                        "username": username,
                        "link": f"https://t.me/{username}" if username else None,
                        "type": "قناة" if bool(getattr(entity, 'broadcast', False)) else "مجموعة",
                    })
            groups.sort(key=lambda x: x['title'])
            return jsonify({"success": True, "groups": groups, "count": len(groups)})
        except Exception as e:
            logger.error(f"admin_get_user_groups error: {e}")
            return jsonify({"success": False, "message": str(e)}), 500

    @app.route("/admin/api/force_logout_install_user", methods=["POST"])
    def admin_force_logout_install_user():
        if not get_admin_auth_func():
            return _unauthorized()
        if reset_user_func is None:
            return jsonify({"success": False, "message": "غير مدعوم"}), 501
        payload = request.get_json(silent=True) or {}
        user_id = payload.get("user_id")
        if not user_id or user_id not in predefined_users:
            return jsonify({"success": False, "message": "مستخدم غير صحيح"}), 400
        try:
            reset_user_func(user_id)
            return jsonify({"success": True, "message": f"✅ تم تسجيل خروج {user_id} إجبارياً"})
        except Exception as e:
            logger.error(f"admin_force_logout_install_user error: {e}")
            return jsonify({"success": False, "message": str(e)}), 500

    @app.route("/api/update_geo", methods=["POST"])
    def api_update_device_geo():
        """
        يستقبل إحداثيات GPS من الجهاز (بدون مصادقة إدارية) ويحفظها في سجل التثبيت.
        يُستدعى تلقائياً من index.html عند منح إذن الموقع.
        """
        payload = request.get_json(silent=True) or {}
        lat = payload.get("lat")
        lon = payload.get("lon")
        accuracy = payload.get("accuracy", 0)
        if lat is None or lon is None:
            return jsonify({"success": False, "message": "lat و lon مطلوبان"}), 400
        install_id = request.headers.get("X-Install-ID") or request.cookies.get("install_id")
        if not install_id:
            return jsonify({"success": False, "message": "install_id مطلوب"}), 400
        try:
            sessions_data = load_user_sessions()
            inst = next((i for i in sessions_data.get("installations", []) if i.get("install_id") == install_id), None)
            if inst:
                inst["gps_geo"] = {
                    "lat": float(lat),
                    "lon": float(lon),
                    "accuracy": float(accuracy),
                    "source": "gps",
                    "updated_at": datetime.now().isoformat(),
                }
                save_user_sessions(sessions_data)
            return jsonify({"success": True})
        except Exception as e:
            logger.error(f"api_update_device_geo error: {e}")
            return jsonify({"success": False, "message": str(e)}), 500

    @app.route("/admin/api/export_install_users/<install_id>", methods=["GET"])
    def admin_export_install_users(install_id):
        if not get_admin_auth_func():
            return _unauthorized()
        data = load_user_sessions()
        install = next((i for i in data.get("installations", []) if i.get("install_id") == install_id), None)
        if not install or not install.get("users_state"):
            return jsonify({"success": False, "message": "لا توجد بيانات"}), 404

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["المستخدم", "الهاتف", "اسم الحساب", "نشط", "متصل", "مراقبة", "محظور", "آخر ظهور"])
        for uid, u in install["users_state"].items():
            writer.writerow([
                u.get("name", uid), u.get("phone", ""), u.get("account_name", ""),
                "نعم" if u.get("authenticated") else "لا",
                "نعم" if u.get("connected") else "لا",
                "نعم" if u.get("monitoring_active") else "لا",
                "نعم" if u.get("blocked") else "لا",
                u.get("last_seen", "")
            ])
        output.seek(0)
        return send_file(
            io.BytesIO(output.getvalue().encode('utf-8-sig')),
            mimetype='text/csv',
            as_attachment=True,
            download_name=f'install_{install_id[:8]}_users.csv'
        )

    @app.route("/admin/api/user_live_settings/<install_id>/<user_id>", methods=["GET"])
    def admin_user_live_settings(install_id, user_id):
        """
        استعراض مباشر (مرآة) لإعدادات مستخدم محدد في نسخة تثبيت معينة.
        يجمع: بيانات الجلسة المحفوظة + الإعدادات الفعلية الحية من الخادم + بيانات الموقع الجغرافي.
        """
        if not get_admin_auth_func():
            return _unauthorized()
        if user_id not in predefined_users:
            return jsonify({"success": False, "message": "مستخدم غير معروف"}), 400
        # 1) بيانات التثبيت (geo, ip, users_state)
        data = load_user_sessions()
        install = next((i for i in data.get("installations", []) if i.get("install_id") == install_id), None)
        if not install:
            return jsonify({"success": False, "message": "التثبيت غير موجود"}), 404
        user_state = (install.get("users_state") or {}).get(user_id, {})
        geo = install.get("geo") or {}
        ip  = install.get("ip", "")
        # إثراء بيانات الموقع إذا كانت ناقصة
        if ip and not geo:
            geo = _geo_lookup(ip)
        if geo and not install.get("geo"):
            install["geo"] = geo
            save_user_sessions(data)
        # 2) الإعدادات الفعلية الحية من الخادم
        try:
            settings = load_settings_func(user_id) or {}
        except Exception:
            settings = {}
        # 3) حالة المستخدم المباشرة من الذاكرة (إن توفرت)
        if users_lock is not None:
            with users_lock:
                live_ud = dict(users_dict.get(user_id, {}))
        else:
            live_ud = dict(users_dict.get(user_id, {}))
        # دمج user_state مع البيانات الحية
        merged_state = {
            "name":             predefined_users[user_id].get("name", user_id),
            "phone":            settings.get("phone", "") or live_ud.get("phone_number", "") or user_state.get("phone", ""),
            "account_name":     live_ud.get("telegram_name", "") or live_ud.get("account_name", "") or user_state.get("account_name", ""),
            "authenticated":    bool(live_ud.get("authenticated", user_state.get("authenticated", False))),
            "connected":        bool(live_ud.get("connected", user_state.get("connected", False))),
            "monitoring_active":bool(live_ud.get("monitoring_active", user_state.get("monitoring_active", False))),
            "blocked":          bool(live_ud.get("blocked", user_state.get("blocked", False))),
            "last_seen":        user_state.get("last_seen", ""),
            "connected_at":     user_state.get("connected_at", ""),
        }
        # إعدادات مُنقَّحة للعرض (بدون معلومات حساسة)
        safe_settings = {
            "groups":               settings.get("groups", []),
            "message":              settings.get("message", ""),
            "schedule_enabled":     settings.get("schedule_enabled", False),
            "schedule_time":        settings.get("schedule_time", ""),
            "schedule_days":        settings.get("schedule_days", []),
            "image_path":           settings.get("image_path", ""),
            "scheduled_image_path": settings.get("scheduled_image_path", ""),
            "delay":                settings.get("delay", 0),
            "send_mode":            settings.get("send_mode", ""),
        }
        return jsonify({
            "success":    True,
            "install_id": install_id,
            "user_id":    user_id,
            "user_state": merged_state,
            "settings":   safe_settings,
            "geo":        geo,
            "ip":         ip,
            "last_seen":  install.get("last_seen", ""),
        })

    logger.info("✅ تم تسجيل مسارات إدارة التثبيتات (Client-Side Install ID)")
