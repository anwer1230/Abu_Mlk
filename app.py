"""
app.py — مركز سرعة إنجاز
╔═══════════════════════════════════════════════════════════════════╗
║   التطبيق الرئيسي — Flask + SocketIO                             ║
║   المرحلة 2: نظام المصادقة الكامل                                ║
║   المستودع الأصلي: https://github.com/anwer1230/Abu_Mlk          ║
╚═══════════════════════════════════════════════════════════════════╝
"""

import os
import time
import logging
import threading

from flask import (
    Flask, render_template, request, jsonify,
    session, redirect, url_for
)
from flask_socketio import SocketIO, emit, join_room, leave_room

from config import Config
from database import Database, get_db
from auth import AuthManager
from upload_handler import UploadHandler
from bot_manager import BotManager

# ── تهيئة السجلات ────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
)
logger = logging.getLogger(__name__)

# ── التأكد من وجود المجلدات ──────────────────────────────────────
Config.ensure_dirs()

# ── تهيئة التطبيق ────────────────────────────────────────────────
app = Flask(__name__)
app.config['SECRET_KEY']              = Config.SECRET_KEY
app.config['DEBUG']                   = Config.DEBUG
app.config['MAX_CONTENT_LENGTH']      = Config.MAX_FILE_SIZE
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE']   = False   # HTTP في التطوير

# ── Socket.IO ────────────────────────────────────────────────────
socketio = SocketIO(
    app,
    cors_allowed_origins='*',
    async_mode='threading',
    logger=False,
    engineio_logger=False,
)

# ── المكونات الرئيسية ─────────────────────────────────────────────
db   = get_db()
auth = AuthManager(db)

# رفع الملفات (المرحلة 7)
upload_handler = UploadHandler(app, db)

# البوتات التفاعلية (المرحلة 8)
bot_manager = BotManager(db)
bot_manager.init_app()

# جلسات Socket.IO النشطة
active_sessions: dict = {}   # {user_id: {'sid': sid, 'rooms': []}}


# ══════════════════════════════════════════════════════════════════
#  الصفحات الرئيسية
# ══════════════════════════════════════════════════════════════════

@app.route('/')
def index():
    """الصفحة الرئيسية — توجيه حسب حالة المصادقة"""
    if auth.is_authenticated():
        return render_template(
            'index.html',
            user_id=session.get('user_id'),
            user_name=session.get('user_name'),
        )
    return redirect(url_for('login_page'))


@app.route('/login')
def login_page():
    """صفحة تسجيل الدخول"""
    if auth.is_authenticated():
        return redirect(url_for('index'))
    return render_template('login.html')


# ══════════════════════════════════════════════════════════════════
#  مسارات المصادقة (API)
# ══════════════════════════════════════════════════════════════════

@app.route('/api/auth/send-code', methods=['POST'])
def api_send_code():
    """إرسال كود التحقق عبر Telegram"""
    data  = request.get_json(force=True) or {}
    phone = (data.get('phone') or '').strip()
    if not phone:
        return jsonify({'success': False, 'message': 'رقم الهاتف مطلوب'}), 400

    db.log_activity(None, 'send_code', f'phone={phone}', request.remote_addr)
    result = auth.send_code(phone)
    return jsonify(result)


@app.route('/api/auth/check-code', methods=['POST'])
def api_check_code():
    """التحقق من كود التحقق"""
    data  = request.get_json(force=True) or {}
    phone = (data.get('phone') or '').strip()
    code  = (data.get('code')  or '').strip()
    if not phone or not code:
        return jsonify({'success': False, 'message': 'بيانات ناقصة'}), 400

    result = auth.check_code(phone, code)
    if result.get('success'):
        logged_user_id = session.get('user_id')
        db.log_activity(logged_user_id, 'login_success',
                        f'phone={phone}', request.remote_addr)
        # مزامنة GitHub فور تسجيل الدخول
        if logged_user_id:
            threading.Thread(
                target=db.backup_to_github,
                args=(logged_user_id,),
                daemon=True,
            ).start()
    return jsonify(result)


@app.route('/api/auth/check-password', methods=['POST'])
def api_check_password():
    """التحقق من كلمة المرور (التحقق الثنائي 2FA)"""
    data     = request.get_json(force=True) or {}
    phone    = (data.get('phone')    or '').strip()
    password = (data.get('password') or '').strip()
    if not phone or not password:
        return jsonify({'success': False, 'message': 'بيانات ناقصة'}), 400

    result = auth.check_password(phone, password)
    if result.get('success'):
        db.log_activity(session.get('user_id'), 'login_2fa_success',
                        f'phone={phone}', request.remote_addr)
    return jsonify(result)


@app.route('/api/auth/logout', methods=['POST'])
def api_logout():
    """تسجيل الخروج"""
    user_id = session.get('user_id')
    db.log_activity(user_id, 'logout', None, request.remote_addr)
    result = auth.logout()
    return jsonify(result)


@app.route('/api/auth/status', methods=['GET'])
def api_auth_status():
    """حالة المصادقة الحالية"""
    return jsonify({
        'is_authenticated': auth.is_authenticated(),
        'user_id':   session.get('user_id'),
        'user_name': session.get('user_name'),
        'phone':     session.get('phone'),
    })


# ══════════════════════════════════════════════════════════════════
#  مسارات المستخدمين
# ══════════════════════════════════════════════════════════════════

@app.route('/api/user/info')
@auth.login_required
def api_user_info():
    """معلومات المستخدم الحالي"""
    user = auth.get_user_info()
    if user:
        return jsonify({'success': True, 'user': user})
    return jsonify({'success': False, 'message': 'مستخدم غير موجود'}), 404


@app.route('/api/users')
@auth.login_required
def api_get_users():
    """جلب جميع المستخدمين المسجلين"""
    users = auth.get_all_users()
    return jsonify({'success': True, 'users': users})


# ══════════════════════════════════════════════════════════════════
#  أحداث Socket.IO (المرحلة 5 — الدردشة الفورية المتقدمة)
# ══════════════════════════════════════════════════════════════════

# مؤقتات مؤشر الكتابة  {chat_id: {user_id: threading.Timer}}
typing_timers: dict = {}


def _stop_typing(chat_id, user_id):
    """إيقاف إشارة الكتابة بعد انتهاء المؤقت."""
    try:
        socketio.emit('user_typing', {
            'user_id':  user_id,
            'chat_id':  chat_id,
            'is_typing': False,
        }, room=f'chat_{chat_id}')
        if chat_id in typing_timers:
            typing_timers[chat_id].pop(user_id, None)
    except Exception:
        pass


@socketio.on('connect')
def handle_connect():
    logger.info(f'✅ عميل متصل: {request.sid}')
    emit('connection_status', {'status': 'connected'})


@socketio.on('disconnect')
def handle_disconnect():
    logger.info(f'❌ عميل منقطع: {request.sid}')
    for user_id, data in list(active_sessions.items()):
        if data.get('sid') == request.sid:
            for room in data.get('rooms', []):
                leave_room(room)
            del active_sessions[user_id]
            break


@socketio.on('register_user')
def handle_register(data):
    """تسجيل المستخدم في Socket.IO"""
    user_id = data.get('user_id')
    if not user_id:
        return
    if not auth.get_user_info(user_id):
        emit('registration_error', {'message': 'مستخدم غير موجود'}, to=request.sid)
        return
    active_sessions[user_id] = {'sid': request.sid, 'rooms': [], 'typing': {}}
    join_room(f'user_{user_id}')
    emit('registration_success', {'success': True, 'user_id': user_id}, to=request.sid)
    logger.info(f'✅ تم تسجيل المستخدم {user_id} في Socket.IO')


@socketio.on('join_chat')
def handle_join_chat(data):
    """الانضمام إلى غرفة محادثة"""
    user_id = data.get('user_id')
    chat_id = data.get('chat_id')
    if not user_id or not chat_id:
        return
    room = f'chat_{chat_id}'
    join_room(room)
    if user_id in active_sessions:
        if room not in active_sessions[user_id]['rooms']:
            active_sessions[user_id]['rooms'].append(room)
    emit('joined_chat', {'chat_id': chat_id, 'status': 'joined'}, to=request.sid)


@socketio.on('leave_chat')
def handle_leave_chat(data):
    """الخروج من غرفة محادثة"""
    user_id = data.get('user_id')
    chat_id = data.get('chat_id')
    if not user_id or not chat_id:
        return
    room = f'chat_{chat_id}'
    leave_room(room)
    if user_id in active_sessions and room in active_sessions[user_id]['rooms']:
        active_sessions[user_id]['rooms'].remove(room)
    emit('left_chat', {'chat_id': chat_id, 'status': 'left'}, to=request.sid)


@socketio.on('send_message')
def handle_send_message(data):
    """إرسال رسالة فورية عبر Socket.IO"""
    user_id    = data.get('user_id')
    chat_id    = data.get('chat_id')
    text       = (data.get('text') or '').strip()
    message_id = data.get('message_id') or f'msg_{int(time.time())}'
    reply_to   = data.get('reply_to')

    if not user_id or not chat_id or not text:
        emit('message_error', {'message_id': message_id, 'error': 'بيانات ناقصة'}, to=request.sid)
        return

    user_info = auth.get_user_info(user_id) or {}
    user_name = user_info.get('name', 'مستخدم')

    msg_obj = {
        'id':         message_id,
        'sender_id':  user_id,
        'sender_name': user_name,
        'chat_id':    chat_id,
        'text':       text,
        'timestamp':  int(time.time()),
        'status':     'sent',
        'reply_to':   reply_to,
    }

    # إرسال عبر Telethon في الخلفية (لا يوقف الرد الفوري)
    def _bg_send():
        try:
            import asyncio
            from auth import load_string_session
            from telethon import TelegramClient
            from telethon.sessions import StringSession
            ss = load_string_session(str(user_id))
            if not ss:
                return
            loop = asyncio.new_event_loop()
            api_id   = int(os.environ.get('TDLIB_API_ID',   '22043994'))
            api_hash = os.environ.get('TDLIB_API_HASH', '56f64582b363d367280db96586b97801')
            async def _send():
                c = TelegramClient(StringSession(ss), api_id, api_hash, loop=loop)
                await c.connect()
                await c.send_message(int(chat_id), text)
                await c.disconnect()
            loop.run_until_complete(_send())
            loop.close()
        except Exception as ex:
            logger.debug(f'bg_send error: {ex}')

    threading.Thread(target=_bg_send, daemon=True).start()

    # بث الرسالة الفورية
    emit('new_message',  {'message': msg_obj}, room=f'chat_{chat_id}')
    emit('message_sent', {'success': True, 'message_id': message_id}, to=request.sid)


@socketio.on('mark_as_read')
def handle_mark_as_read(data):
    """تحديث حالة القراءة"""
    user_id     = data.get('user_id')
    chat_id     = data.get('chat_id')
    message_ids = data.get('message_ids', [])
    if not user_id or not chat_id or not message_ids:
        return
    emit('messages_read', {
        'chat_id':     chat_id,
        'message_ids': message_ids,
        'reader_id':   user_id,
    }, room=f'chat_{chat_id}')


@socketio.on('typing_start')
def handle_typing_start(data):
    """بدء مؤشر الكتابة"""
    user_id = data.get('user_id')
    chat_id = data.get('chat_id')
    if not user_id or not chat_id:
        return

    # إلغاء المؤقت السابق
    if chat_id in typing_timers and user_id in typing_timers[chat_id]:
        typing_timers[chat_id][user_id].cancel()

    emit('user_typing', {
        'user_id':  user_id,
        'chat_id':  chat_id,
        'is_typing': True,
    }, room=f'chat_{chat_id}', skip_sid=request.sid)

    # مؤقت 3 ثوانٍ لإيقاف الإشارة تلقائياً
    t = threading.Timer(3.0, _stop_typing, args=(chat_id, user_id))
    t.daemon = True
    t.start()
    typing_timers.setdefault(chat_id, {})[user_id] = t


@socketio.on('typing_stop')
def handle_typing_stop(data):
    """إيقاف مؤشر الكتابة"""
    user_id = data.get('user_id')
    chat_id = data.get('chat_id')
    if not user_id or not chat_id:
        return
    if chat_id in typing_timers and user_id in typing_timers[chat_id]:
        typing_timers[chat_id][user_id].cancel()
        del typing_timers[chat_id][user_id]
    emit('user_typing', {
        'user_id':  user_id,
        'chat_id':  chat_id,
        'is_typing': False,
    }, room=f'chat_{chat_id}', skip_sid=request.sid)


@socketio.on('delete_message')
def handle_delete_message(data):
    """حذف رسالة"""
    user_id    = data.get('user_id')
    chat_id    = data.get('chat_id')
    message_id = data.get('message_id')
    if not user_id or not chat_id or not message_id:
        return

    def _bg_delete():
        try:
            import asyncio
            from auth import load_string_session
            from telethon import TelegramClient
            from telethon.sessions import StringSession
            ss = load_string_session(str(user_id))
            if not ss:
                return
            loop = asyncio.new_event_loop()
            api_id   = int(os.environ.get('TDLIB_API_ID',   '22043994'))
            api_hash = os.environ.get('TDLIB_API_HASH', '56f64582b363d367280db96586b97801')
            async def _del():
                c = TelegramClient(StringSession(ss), api_id, api_hash, loop=loop)
                await c.connect()
                await c.delete_messages(int(chat_id), [int(message_id)])
                await c.disconnect()
            loop.run_until_complete(_del())
            loop.close()
        except Exception as ex:
            logger.debug(f'bg_delete error: {ex}')

    threading.Thread(target=_bg_delete, daemon=True).start()
    emit('message_deleted', {
        'chat_id':    chat_id,
        'message_id': message_id,
        'deleted_by': user_id,
    }, room=f'chat_{chat_id}')


@socketio.on('edit_message')
def handle_edit_message(data):
    """تعديل رسالة"""
    user_id    = data.get('user_id')
    chat_id    = data.get('chat_id')
    message_id = data.get('message_id')
    new_text   = (data.get('text') or '').strip()
    if not user_id or not chat_id or not message_id or not new_text:
        return

    def _bg_edit():
        try:
            import asyncio
            from auth import load_string_session
            from telethon import TelegramClient
            from telethon.sessions import StringSession
            ss = load_string_session(str(user_id))
            if not ss:
                return
            loop = asyncio.new_event_loop()
            api_id   = int(os.environ.get('TDLIB_API_ID',   '22043994'))
            api_hash = os.environ.get('TDLIB_API_HASH', '56f64582b363d367280db96586b97801')
            async def _edit():
                c = TelegramClient(StringSession(ss), api_id, api_hash, loop=loop)
                await c.connect()
                await c.edit_message(int(chat_id), int(message_id), new_text)
                await c.disconnect()
            loop.run_until_complete(_edit())
            loop.close()
        except Exception as ex:
            logger.debug(f'bg_edit error: {ex}')

    threading.Thread(target=_bg_edit, daemon=True).start()
    emit('message_edited', {
        'chat_id':    chat_id,
        'message_id': message_id,
        'new_text':   new_text,
        'edited_by':  user_id,
        'edited_at':  int(time.time()),
    }, room=f'chat_{chat_id}')


@socketio.on('get_online_status')
def handle_get_online_status(data):
    """حالة اتصال مستخدم معين"""
    target = data.get('target_user_id')
    if not target:
        return
    is_online = target in active_sessions
    emit('online_status', {
        'user_id':   target,
        'is_online': is_online,
        'last_seen': int(time.time()) if not is_online else None,
    }, to=request.sid)


@socketio.on('get_chat_participants')
def handle_get_chat_participants(data):
    """المشاركون المتصلون في محادثة"""
    chat_id = data.get('chat_id')
    if not chat_id:
        return
    participants = [
        {'user_id': uid, 'is_online': True}
        for uid, sess in active_sessions.items()
        if f'chat_{chat_id}' in sess.get('rooms', [])
    ]
    emit('chat_participants', {
        'chat_id':      chat_id,
        'participants': participants,
        'count':        len(participants),
    }, to=request.sid)


# ══════════════════════════════════════════════════════════════════
#  مسارات المحادثات والرسائل (المرحلة 4)
# ══════════════════════════════════════════════════════════════════

def _run_telethon(user_id: str, coro):
    """تشغيل coroutine لـ Telethon بشكل متزامن (thread-safe)."""
    from auth import load_string_session, SESSIONS_DIR
    import asyncio
    from telethon import TelegramClient
    from telethon.sessions import StringSession

    session_str = load_string_session(str(user_id))
    if not session_str:
        raise RuntimeError('لا توجد جلسة محفوظة')

    api_id   = int(os.environ.get('TDLIB_API_ID',   '22043994'))
    api_hash = os.environ.get('TDLIB_API_HASH', '56f64582b363d367280db96586b97801')

    loop = asyncio.new_event_loop()
    try:
        client = TelegramClient(StringSession(session_str), api_id, api_hash, loop=loop)
        async def _run():
            await client.connect()
            result = await coro(client)
            await client.disconnect()
            return result
        return loop.run_until_complete(_run())
    finally:
        loop.close()


@app.route('/api/chats', methods=['GET'])
def get_chats():
    """جلب قائمة المحادثات عبر Telethon"""
    if not auth.is_authenticated():
        return jsonify({'success': False, 'message': 'غير مسجل الدخول'}), 401

    user_id = session.get('user_id')
    try:
        async def _fetch(client):
            dialogs = await client.get_dialogs(limit=100)
            chats = []
            for d in dialogs:
                entity = d.entity
                last_msg = d.message

                # نص آخر رسالة
                last_text = ''
                last_time = None
                if last_msg:
                    last_text = getattr(last_msg, 'message', '') or ''
                    last_time = int(last_msg.date.timestamp()) if last_msg.date else None

                # تفاصيل الكيان
                name = getattr(entity, 'title', None) or \
                       f"{getattr(entity,'first_name','') or ''} {getattr(entity,'last_name','') or ''}".strip() or \
                       'مستخدم'

                chats.append({
                    'id':                d.id,
                    'name':              name,
                    'type':              type(entity).__name__,
                    'is_online':         False,
                    'is_pinned':         getattr(d, 'pinned', False),
                    'is_muted':          False,
                    'unread_count':      d.unread_count or 0,
                    'last_message':      last_text,
                    'last_message_time': last_time,
                })
            return chats

        chats = _run_telethon(user_id, _fetch)
        return jsonify({'success': True, 'chats': chats})

    except Exception as e:
        logger.error(f'get_chats error: {e}')
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/chats/<int:chat_id>/messages', methods=['GET'])
def get_chat_messages(chat_id):
    """جلب رسائل محادثة محددة"""
    if not auth.is_authenticated():
        return jsonify({'success': False, 'message': 'غير مسجل الدخول'}), 401

    user_id = session.get('user_id')
    limit   = request.args.get('limit', 50, type=int)

    try:
        async def _fetch(client):
            msgs = await client.get_messages(chat_id, limit=limit)
            result = []
            me = await client.get_me()
            for msg in reversed(msgs):
                sender = await msg.get_sender()
                if sender:
                    sender_name = getattr(sender, 'title', None) or \
                                  f"{getattr(sender,'first_name','') or ''} {getattr(sender,'last_name','') or ''}".strip()
                    sender_id   = str(sender.id)
                else:
                    sender_name = 'مستخدم'
                    sender_id   = None

                result.append({
                    'id':          msg.id,
                    'sender_id':   sender_id,
                    'sender_name': sender_name or 'مستخدم',
                    'text':        msg.message or '',
                    'timestamp':   int(msg.date.timestamp()) if msg.date else None,
                    'status':      'read',
                    'media':       type(msg.media).__name__ if msg.media else None,
                })
            return result

        messages = _run_telethon(user_id, _fetch)
        return jsonify({'success': True, 'messages': messages})

    except Exception as e:
        logger.error(f'get_chat_messages error: {e}')
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/messages/send', methods=['POST'])
def api_send_message():
    """إرسال رسالة نصية عبر Telethon"""
    if not auth.is_authenticated():
        return jsonify({'success': False, 'message': 'غير مسجل الدخول'}), 401

    data       = request.get_json(force=True) or {}
    chat_id    = data.get('chat_id')
    text       = (data.get('text') or '').strip()
    message_id = data.get('message_id')

    if not chat_id or not text:
        return jsonify({'success': False, 'message': 'بيانات ناقصة'}), 400

    user_id = session.get('user_id')

    try:
        async def _send(client):
            msg = await client.send_message(int(chat_id), text)
            return msg.id

        sent_id = _run_telethon(user_id, _send)

        # بث الرسالة عبر Socket.IO لجميع المستمعين
        socketio.emit('new_message', {
            'message': {
                'id':          message_id or sent_id,
                'sender_id':   user_id,
                'chat_id':     chat_id,
                'text':        text,
                'timestamp':   int(time.time()),
                'status':      'sent',
            }
        })

        return jsonify({'success': True, 'message_id': sent_id})

    except Exception as e:
        logger.error(f'api_send_message error: {e}')
        return jsonify({'success': False, 'message': str(e)}), 500


# ══════════════════════════════════════════════════════════════════
#  مسارات المجلدات المشتركة (المرحلة 6)
# ══════════════════════════════════════════════════════════════════

def _folder_member(conn, folder_id, user_id, min_level=1):
    """التحقق من أن المستخدم عضو بالمستوى المطلوب."""
    row = conn.execute(
        'SELECT permission_level FROM folder_members WHERE folder_id=? AND user_id=?',
        (folder_id, str(user_id))
    ).fetchone()
    return row and row['permission_level'] >= min_level


def _get_folder_name(folder_id: int) -> str:
    with db.get_connection() as conn:
        row = conn.execute('SELECT name FROM shared_folders WHERE id=?', (folder_id,)).fetchone()
    return row['name'] if row else 'مجلد'


def _notify_folder_members(folder_id: int, event_name: str, data: dict):
    with db.get_connection() as conn:
        rows = conn.execute(
            'SELECT user_id FROM folder_members WHERE folder_id=?', (folder_id,)
        ).fetchall()
    for r in rows:
        socketio.emit(event_name, {'folder_id': folder_id, **data},
                      room=f'user_{r["user_id"]}')


@app.route('/api/folders', methods=['GET'])
@auth.login_required
def get_folders():
    user_id = session.get('user_id')
    with db.get_connection() as conn:
        rows = conn.execute('''
            SELECT DISTINCT f.*,
                (SELECT COUNT(*) FROM folder_members fm WHERE fm.folder_id = f.id) AS member_count,
                (SELECT COUNT(*) FROM folder_chats  fc WHERE fc.folder_id  = f.id) AS chat_count
            FROM shared_folders f
            LEFT JOIN folder_members fm2 ON f.id = fm2.folder_id
            WHERE f.owner_id = ? OR fm2.user_id = ?
            ORDER BY f.created_at DESC
        ''', (user_id, user_id)).fetchall()
        # جلب معرّفات المحادثات لكل مجلد
        folders = []
        for row in rows:
            f = dict(row)
            chat_rows = conn.execute(
                'SELECT chat_id FROM folder_chats WHERE folder_id=?', (f['id'],)
            ).fetchall()
            f['chat_ids'] = [r['chat_id'] for r in chat_rows]
            folders.append(f)
    return jsonify({'success': True, 'folders': folders})


@app.route('/api/folders', methods=['POST'])
@auth.login_required
def create_folder():
    user_id    = session.get('user_id')
    data       = request.get_json(force=True) or {}
    name       = (data.get('name') or '').strip()
    chat_ids   = data.get('chat_ids', [])
    member_ids = data.get('member_ids', [])
    icon       = data.get('icon', '📁')

    if not name:
        return jsonify({'success': False, 'message': 'اسم المجلد مطلوب'}), 400

    with db.get_connection() as conn:
        cur = conn.cursor()
        cur.execute('INSERT INTO shared_folders (name, icon, owner_id) VALUES (?,?,?)',
                    (name, icon, user_id))
        folder_id = cur.lastrowid
        cur.execute('INSERT INTO folder_members (folder_id, user_id, permission_level) VALUES (?,?,2)',
                    (folder_id, user_id))
        for chat_id in chat_ids:
            cur.execute('INSERT OR IGNORE INTO folder_chats (folder_id, chat_id) VALUES (?,?)',
                        (folder_id, str(chat_id)))
        for mid in member_ids:
            if str(mid) != str(user_id):
                cur.execute(
                    'INSERT OR IGNORE INTO folder_members (folder_id, user_id, permission_level) VALUES (?,?,1)',
                    (folder_id, str(mid))
                )
                socketio.emit('folder_invitation', {
                    'folder_id':       folder_id,
                    'folder_name':     name,
                    'invited_by':      user_id,
                    'invited_by_name': session.get('user_name', 'مستخدم'),
                }, room=f'user_{mid}')

    # مزامنة GitHub بعد إنشاء المجلد
    threading.Thread(
        target=db.backup_to_github,
        args=(user_id,),
        daemon=True,
    ).start()

    return jsonify({'success': True, 'folder_id': folder_id})


@app.route('/api/folders/<int:folder_id>', methods=['DELETE'])
@auth.login_required
def delete_folder(folder_id):
    user_id = session.get('user_id')
    with db.get_connection() as conn:
        row = conn.execute('SELECT owner_id FROM shared_folders WHERE id=?', (folder_id,)).fetchone()
        if not row:
            return jsonify({'success': False, 'message': 'المجلد غير موجود'}), 404
        if row['owner_id'] != user_id:
            return jsonify({'success': False, 'message': 'ليس لديك صلاحية الحذف'}), 403
        conn.execute('DELETE FROM folder_chats   WHERE folder_id=?', (folder_id,))
        conn.execute('DELETE FROM folder_members WHERE folder_id=?', (folder_id,))
        conn.execute('DELETE FROM shared_folders WHERE id=?',        (folder_id,))
    return jsonify({'success': True, 'message': 'تم حذف المجلد'})


@app.route('/api/folders/<int:folder_id>/chats', methods=['POST'])
@auth.login_required
def add_chat_to_folder(folder_id):
    user_id = session.get('user_id')
    data    = request.get_json(force=True) or {}
    chat_id = str(data.get('chat_id', ''))
    if not chat_id:
        return jsonify({'success': False, 'message': 'معرّف المحادثة مطلوب'}), 400
    with db.get_connection() as conn:
        if not _folder_member(conn, folder_id, user_id, min_level=1):
            return jsonify({'success': False, 'message': 'ليس لديك صلاحية'}), 403
        conn.execute('INSERT OR IGNORE INTO folder_chats (folder_id, chat_id) VALUES (?,?)',
                     (folder_id, chat_id))
    _notify_folder_members(folder_id, 'folder_update',
                           {'action': 'chat_added', 'chat_id': chat_id, 'added_by': user_id})
    return jsonify({'success': True, 'message': 'تم إضافة المحادثة'})


@app.route('/api/folders/<int:folder_id>/chats/<chat_id>', methods=['DELETE'])
@auth.login_required
def remove_chat_from_folder(folder_id, chat_id):
    user_id = session.get('user_id')
    with db.get_connection() as conn:
        if not _folder_member(conn, folder_id, user_id, min_level=1):
            return jsonify({'success': False, 'message': 'ليس لديك صلاحية'}), 403
        conn.execute('DELETE FROM folder_chats WHERE folder_id=? AND chat_id=?',
                     (folder_id, str(chat_id)))
    _notify_folder_members(folder_id, 'folder_update',
                           {'action': 'chat_removed', 'chat_id': chat_id, 'removed_by': user_id})
    return jsonify({'success': True, 'message': 'تم إزالة المحادثة'})


@app.route('/api/folders/<int:folder_id>/members', methods=['POST'])
@auth.login_required
def add_folder_member(folder_id):
    user_id       = session.get('user_id')
    data          = request.get_json(force=True) or {}
    new_member_id = str(data.get('user_id', ''))
    permission    = int(data.get('permission_level', 1))
    if not new_member_id:
        return jsonify({'success': False, 'message': 'معرّف المستخدم مطلوب'}), 400
    with db.get_connection() as conn:
        if not _folder_member(conn, folder_id, user_id, min_level=2):
            return jsonify({'success': False, 'message': 'ليس لديك صلاحية الإضافة'}), 403
        conn.execute(
            'INSERT OR IGNORE INTO folder_members (folder_id, user_id, permission_level) VALUES (?,?,?)',
            (folder_id, new_member_id, permission)
        )
    socketio.emit('folder_invitation', {
        'folder_id':       folder_id,
        'folder_name':     _get_folder_name(folder_id),
        'invited_by':      user_id,
        'invited_by_name': session.get('user_name', 'مستخدم'),
    }, room=f'user_{new_member_id}')
    return jsonify({'success': True, 'message': 'تم إضافة العضو'})


@app.route('/api/folders/<int:folder_id>/members/<member_user_id>', methods=['DELETE'])
@auth.login_required
def remove_folder_member(folder_id, member_user_id):
    user_id = session.get('user_id')
    with db.get_connection() as conn:
        if not _folder_member(conn, folder_id, user_id, min_level=2):
            return jsonify({'success': False, 'message': 'ليس لديك صلاحية'}), 403
        row = conn.execute('SELECT owner_id FROM shared_folders WHERE id=?', (folder_id,)).fetchone()
        if row and row['owner_id'] == member_user_id:
            return jsonify({'success': False, 'message': 'لا يمكن إزالة المالك'}), 400
        conn.execute('DELETE FROM folder_members WHERE folder_id=? AND user_id=?',
                     (folder_id, member_user_id))
    return jsonify({'success': True, 'message': 'تم إزالة العضو'})


# ══════════════════════════════════════════════════════════════════
#  مسارات البوتات (المرحلة 8)
# ══════════════════════════════════════════════════════════════════

@app.route('/api/bots', methods=['GET'])
@auth.login_required
def api_get_bots():
    """قائمة البوتات المسجّلة"""
    bots = bot_manager.list_bots()
    # إزالة الحقول الحساسة قبل الإرسال
    safe = [{k: v for k, v in b.items() if k not in ('handler', 'api_hash')}
            for b in bots]
    return jsonify({'success': True, 'bots': safe})


@app.route('/api/bots', methods=['POST'])
@auth.login_required
def api_create_bot():
    """تسجيل بوت جديد"""
    user_id = session.get('user_id')
    data    = request.get_json(force=True) or {}
    name    = (data.get('name') or '').strip()
    if not name:
        return jsonify({'success': False, 'message': 'اسم البوت مطلوب'}), 400

    bot_id = bot_manager.register_bot(
        name     = name,
        phone    = data.get('phone'),
        api_id   = data.get('api_id'),
        api_hash = data.get('api_hash'),
        user_id  = user_id,
    )
    db.log_activity(user_id, 'bot_created', f'name={name}', request.remote_addr)
    return jsonify({'success': True, 'bot_id': bot_id, 'name': name})


@app.route('/api/bots/<bot_name>', methods=['DELETE'])
@auth.login_required
def api_delete_bot(bot_name):
    """حذف بوت"""
    user_id = session.get('user_id')
    bots    = bot_manager.list_bots()
    bot     = next((b for b in bots if b.get('name') == bot_name), None)
    if not bot:
        return jsonify({'success': False, 'message': 'البوت غير موجود'}), 404
    with db.get_connection() as conn:
        conn.execute('DELETE FROM bots WHERE name=?', (bot_name,))
        conn.execute('DELETE FROM bot_commands WHERE bot_id=?', (bot.get('id', 0),))
    db.log_activity(user_id, 'bot_deleted', f'name={bot_name}', request.remote_addr)
    return jsonify({'success': True})


@app.route('/api/bots/<bot_name>/commands', methods=['GET'])
@auth.login_required
def api_bot_commands(bot_name):
    """أوامر بوت"""
    with db.get_connection() as conn:
        bot = conn.execute('SELECT id FROM bots WHERE name=?', (bot_name,)).fetchone()
        if not bot:
            return jsonify({'success': False, 'message': 'البوت غير موجود'}), 404
        rows = conn.execute('SELECT * FROM bot_commands WHERE bot_id=? ORDER BY created_at DESC LIMIT 100',
                            (bot['id'],)).fetchall()
    return jsonify({'success': True, 'commands': [dict(r) for r in rows]})


@app.route('/api/bots/<bot_name>/message', methods=['POST'])
@auth.login_required
def api_bot_message(bot_name):
    """إرسال رسالة لبوت لمعالجتها (اختبار)"""
    user_id = session.get('user_id')
    data    = request.get_json(force=True) or {}
    text    = (data.get('text') or '').strip()
    if not text:
        return jsonify({'success': False, 'message': 'النص مطلوب'}), 400

    reply = bot_manager.handle_message(
        bot_name  = bot_name,
        sender_id = str(user_id),
        text      = text,
    )
    return jsonify({'success': True, 'reply': reply})


# ══════════════════════════════════════════════════════════════════
#  المرحلة 1: تفاعلات + سياق الرسائل + بحث + ملف شخصي + إعدادات
# ══════════════════════════════════════════════════════════════════

@app.route('/api/messages/reaction', methods=['POST'])
@auth.login_required
def api_msg_reaction():
    user_id = session.get('user_id')
    data    = request.get_json(force=True) or {}
    msg_id  = str(data.get('message_id', ''))
    reaction= (data.get('reaction') or '').strip()
    action  = data.get('action', 'add')
    chat_id = data.get('chat_id')
    if not msg_id or not reaction:
        return jsonify({'success': False, 'message': 'بيانات ناقصة'}), 400
    with db.get_connection() as conn:
        if action == 'add':
            conn.execute('INSERT OR REPLACE INTO message_reactions (message_id,user_id,reaction) VALUES (?,?,?)',
                         (msg_id, user_id, reaction))
        else:
            conn.execute('DELETE FROM message_reactions WHERE message_id=? AND user_id=? AND reaction=?',
                         (msg_id, user_id, reaction))
        rows = conn.execute('SELECT user_id, reaction FROM message_reactions WHERE message_id=?',
                            (msg_id,)).fetchall()
    rxns = [{'user_id': r['user_id'], 'reaction': r['reaction']} for r in rows]
    if chat_id:
        socketio.emit('message_reaction_update',
                      {'message_id': msg_id, 'reactions': rxns},
                      room=f'chat_{chat_id}')
    return jsonify({'success': True, 'reactions': rxns})


@app.route('/api/messages/reactions', methods=['GET'])
@auth.login_required
def api_get_reactions():
    raw  = request.args.get('ids', '')
    ids  = [i.strip() for i in raw.split(',') if i.strip()]
    if not ids:
        return jsonify({'success': True, 'reactions': {}})
    result = {}
    with db.get_connection() as conn:
        for mid in ids:
            rows = conn.execute('SELECT user_id, reaction FROM message_reactions WHERE message_id=?',
                                (mid,)).fetchall()
            if rows:
                result[mid] = [{'user_id': r['user_id'], 'reaction': r['reaction']} for r in rows]
    return jsonify({'success': True, 'reactions': result})


@app.route('/api/messages/forward', methods=['POST'])
@auth.login_required
def api_forward_messages():
    user_id     = session.get('user_id')
    data        = request.get_json(force=True) or {}
    to_chat_id  = data.get('to_chat_id')
    from_chat_id= data.get('from_chat_id')
    message_ids = data.get('message_ids', [])
    if not to_chat_id or not message_ids:
        return jsonify({'success': False, 'message': 'بيانات ناقصة'}), 400
    try:
        async def _fwd(client):
            from telethon.errors import FloodWaitError
            results = []
            for mid in message_ids:
                try:
                    msgs = await client.forward_messages(
                        entity   = int(to_chat_id),
                        messages = [int(mid)],
                        from_peer= int(from_chat_id) if from_chat_id else int(to_chat_id),
                    )
                    results.append(msgs[0].id if msgs else None)
                except Exception:
                    pass
            return results
        ids = _run_telethon(user_id, _fwd)
        return jsonify({'success': True, 'forwarded': len(ids)})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/messages/pin', methods=['POST'])
@auth.login_required
def api_pin_message():
    user_id = session.get('user_id')
    data    = request.get_json(force=True) or {}
    msg_id  = data.get('message_id')
    chat_id = data.get('chat_id')
    if not msg_id or not chat_id:
        return jsonify({'success': False, 'message': 'بيانات ناقصة'}), 400
    with db.get_connection() as conn:
        conn.execute('INSERT OR IGNORE INTO pinned_messages (chat_id,message_id,user_id) VALUES (?,?,?)',
                     (str(chat_id), str(msg_id), user_id))
    try:
        async def _pin(client):
            await client.pin_message(entity=int(chat_id), message=int(msg_id))
        _run_telethon(user_id, _pin)
    except Exception as e:
        logger.warning(f'pin_message Telethon: {e}')
    return jsonify({'success': True, 'message': 'تم تثبيت الرسالة'})


@app.route('/api/messages/bookmark', methods=['POST'])
@auth.login_required
def api_bookmark_message():
    user_id = session.get('user_id')
    data    = request.get_json(force=True) or {}
    msg_id  = str(data.get('message_id', ''))
    chat_id = str(data.get('chat_id', ''))
    text    = (data.get('text') or '')[:1000]
    if not msg_id:
        return jsonify({'success': False, 'message': 'message_id مطلوب'}), 400
    with db.get_connection() as conn:
        conn.execute('INSERT OR REPLACE INTO message_bookmarks (message_id,chat_id,user_id,text) VALUES (?,?,?,?)',
                     (msg_id, chat_id, user_id, text))
    return jsonify({'success': True, 'message': 'تم الحفظ'})


@app.route('/api/messages/bookmarks', methods=['GET'])
@auth.login_required
def api_get_bookmarks():
    user_id = session.get('user_id')
    with db.get_connection() as conn:
        rows = conn.execute(
            'SELECT * FROM message_bookmarks WHERE user_id=? ORDER BY created_at DESC LIMIT 100',
            (user_id,)
        ).fetchall()
    return jsonify({'success': True, 'bookmarks': [dict(r) for r in rows]})


@app.route('/api/chats/<int:chat_id>/archive', methods=['POST'])
@auth.login_required
def api_archive_chat(chat_id):
    user_id = session.get('user_id')
    data    = request.get_json(force=True) or {}
    action  = data.get('action', 'archive')
    with db.get_connection() as conn:
        if action == 'archive':
            conn.execute('INSERT OR IGNORE INTO archived_chats (chat_id,user_id) VALUES (?,?)',
                         (str(chat_id), user_id))
        else:
            conn.execute('DELETE FROM archived_chats WHERE chat_id=? AND user_id=?',
                         (str(chat_id), user_id))
    return jsonify({'success': True})


@app.route('/api/chats/<int:chat_id>/mute', methods=['POST'])
@auth.login_required
def api_mute_chat(chat_id):
    user_id = session.get('user_id')
    data    = request.get_json(force=True) or {}
    action  = data.get('action', 'mute')
    hours   = int(data.get('hours', 8))
    with db.get_connection() as conn:
        if action == 'mute':
            from datetime import timedelta
            until = (time.strftime('%Y-%m-%d %H:%M:%S',
                                   time.gmtime(time.time() + hours * 3600)))
            conn.execute('INSERT OR REPLACE INTO muted_chats (chat_id,user_id,muted_until) VALUES (?,?,?)',
                         (str(chat_id), user_id, until))
        else:
            conn.execute('DELETE FROM muted_chats WHERE chat_id=? AND user_id=?',
                         (str(chat_id), user_id))
    return jsonify({'success': True})


@app.route('/api/chats/states', methods=['GET'])
@auth.login_required
def api_chat_states():
    user_id = session.get('user_id')
    with db.get_connection() as conn:
        arc = [r['chat_id'] for r in conn.execute(
            'SELECT chat_id FROM archived_chats WHERE user_id=?', (user_id,)).fetchall()]
        muted = [r['chat_id'] for r in conn.execute(
            'SELECT chat_id FROM muted_chats WHERE user_id=?', (user_id,)).fetchall()]
    return jsonify({'success': True, 'archived': arc, 'muted': muted})


@app.route('/api/users/<int:target_user_id>/block', methods=['POST', 'DELETE'])
@auth.login_required
def api_block_user(target_user_id):
    user_id = session.get('user_id')
    is_block = request.method == 'POST'
    with db.get_connection() as conn:
        if is_block:
            conn.execute('INSERT OR IGNORE INTO blocked_users (user_id,blocked_user_id) VALUES (?,?)',
                         (user_id, str(target_user_id)))
        else:
            conn.execute('DELETE FROM blocked_users WHERE user_id=? AND blocked_user_id=?',
                         (user_id, str(target_user_id)))
    try:
        async def _blk(client):
            from telethon.tl.functions.contacts import BlockRequest, UnblockRequest
            if is_block:
                await client(BlockRequest(id=target_user_id))
            else:
                await client(UnblockRequest(id=target_user_id))
        _run_telethon(user_id, _blk)
    except Exception as e:
        logger.warning(f'block_user Telethon: {e}')
    msg = 'تم الحظر' if is_block else 'تم إلغاء الحظر'
    return jsonify({'success': True, 'message': msg})


@app.route('/api/search', methods=['GET'])
@auth.login_required
def api_search():
    user_id = session.get('user_id')
    q       = (request.args.get('q') or '').strip()
    chat_id = request.args.get('chat_id')
    if not q:
        return jsonify({'success': False, 'message': 'كلمة البحث مطلوبة'}), 400
    try:
        async def _search(client):
            entity = int(chat_id) if chat_id else 'me'
            msgs   = await client.get_messages(entity, search=q, limit=40)
            results = []
            me = await client.get_me()
            for msg in msgs:
                sender = await msg.get_sender()
                sname  = getattr(sender, 'title', None) or \
                         f"{getattr(sender,'first_name','') or ''} {getattr(sender,'last_name','') or ''}".strip() \
                         if sender else 'مستخدم'
                results.append({
                    'id':          msg.id,
                    'chat_id':     chat_id or str(me.id),
                    'sender_name': sname,
                    'text':        msg.message or '',
                    'timestamp':   int(msg.date.timestamp()) if msg.date else None,
                })
            return results
        results = _run_telethon(user_id, _search)
        return jsonify({'success': True, 'results': results})
    except Exception as e:
        logger.error(f'api_search: {e}')
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/profile/<int:target_id>', methods=['GET'])
@auth.login_required
def api_get_profile(target_id):
    user_id = session.get('user_id')
    try:
        async def _prof(client):
            entity = await client.get_entity(target_id)
            return {
                'id':       target_id,
                'name':     getattr(entity, 'title', None) or
                            f"{getattr(entity,'first_name','') or ''} {getattr(entity,'last_name','') or ''}".strip(),
                'username': getattr(entity, 'username', None),
                'phone':    getattr(entity, 'phone', None),
                'bio':      getattr(getattr(entity, 'full', None), 'about', None),
            }
        profile = _run_telethon(user_id, _prof)
        return jsonify({'success': True, 'profile': profile})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/settings', methods=['GET'])
@auth.login_required
def api_get_settings():
    user_id = session.get('user_id')
    settings = db.get_all_settings(user_id)
    return jsonify({'success': True, 'settings': settings})


@app.route('/api/settings', methods=['POST'])
@auth.login_required
def api_update_setting():
    user_id = session.get('user_id')
    data    = request.get_json(force=True) or {}
    key     = (data.get('key') or '').strip()
    value   = data.get('value')
    if not key:
        return jsonify({'success': False, 'message': 'key مطلوب'}), 400
    db.set_setting(user_id, key, value)
    return jsonify({'success': True})


@app.route('/api/translate', methods=['POST'])
@auth.login_required
def api_translate():
    """ترجمة نص — يستخدم Groq إن كان متاحاً"""
    data = request.get_json(force=True) or {}
    text = (data.get('text') or '').strip()
    if not text:
        return jsonify({'success': False, 'message': 'النص مطلوب'}), 400
    groq_key = os.environ.get('GROQ_API_KEY')
    if not groq_key:
        return jsonify({'success': True, 'translation': f'[ترجمة] {text}'})
    try:
        import requests as req_lib
        resp = req_lib.post(
            'https://api.groq.com/openai/v1/chat/completions',
            headers={'Authorization': f'Bearer {groq_key}',
                     'Content-Type': 'application/json'},
            json={'model': 'llama3-8b-8192',
                  'messages': [{'role': 'user',
                                'content': f'ترجم هذا النص إلى العربية فقط بدون شرح:\n{text}'}],
                  'max_tokens': 300},
            timeout=10,
        )
        translation = resp.json()['choices'][0]['message']['content'].strip()
        return jsonify({'success': True, 'translation': translation})
    except Exception as e:
        return jsonify({'success': True, 'translation': text, 'note': str(e)})


# ══════════════════════════════════════════════════════════════════
#  المرحلة 2: إنشاء المجموعات + إرسال الوسائط
# ══════════════════════════════════════════════════════════════════

@app.route('/api/groups/create', methods=['POST'])
@auth.login_required
def api_create_group():
    user_id = session.get('user_id')
    data    = request.get_json(force=True) or {}
    title   = (data.get('title') or '').strip()
    gtype   = data.get('type', 'group')   # group | supergroup | channel
    users   = [u.strip() for u in str(data.get('users', '')).split(',') if u.strip()]

    if not title:
        return jsonify({'success': False, 'message': 'اسم المجموعة مطلوب'}), 400

    try:
        async def _create(client):
            from telethon.tl.functions.messages import CreateChatRequest
            from telethon.tl.functions.channels import CreateChannelRequest

            # حل معرفات المستخدمين
            resolved = []
            for u in users:
                try:
                    entity = await client.get_entity(u)
                    resolved.append(entity)
                except Exception:
                    pass

            if gtype in ('supergroup', 'channel'):
                is_channel = (gtype == 'channel')
                result = await client(CreateChannelRequest(
                    title      = title,
                    about      = '',
                    megagroup  = not is_channel,
                    broadcast  = is_channel,
                ))
                chat = result.chats[0]
                chat_id = chat.id
            else:
                if not resolved:
                    return {'success': False, 'message': 'أضف عضواً واحداً على الأقل'}
                result = await client(CreateChatRequest(
                    users = resolved,
                    title = title,
                ))
                chat    = result.chats[0]
                chat_id = chat.id

            return {'success': True, 'chat_id': chat_id, 'title': title}

        result = _run_telethon(user_id, _create)
        if isinstance(result, dict) and not result.get('success', True):
            return jsonify(result), 400
        return jsonify(result)
    except Exception as e:
        logger.error(f'create_group: {e}')
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/groups/<int:chat_id>/leave', methods=['POST'])
@auth.login_required
def api_leave_group(chat_id):
    user_id = session.get('user_id')
    try:
        async def _leave(client):
            from telethon.tl.functions.channels import LeaveChannelRequest
            from telethon.tl.functions.messages import DeleteChatUserRequest
            try:
                await client(LeaveChannelRequest(channel=chat_id))
            except Exception:
                me = await client.get_me()
                await client(DeleteChatUserRequest(chat_id=chat_id, user_id=me))
        _run_telethon(user_id, _leave)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/messages/send-media', methods=['POST'])
@auth.login_required
def api_send_media():
    """إرسال وسائط (صور/فيديو/ملفات) عبر Telethon"""
    import tempfile, os as _os
    user_id = session.get('user_id')
    chat_id = request.form.get('chat_id') or request.form.get('chat_id')
    caption = request.form.get('caption', '')

    if not chat_id:
        return jsonify({'success': False, 'message': 'chat_id مطلوب'}), 400

    files = request.files.getlist('files')
    if not files:
        return jsonify({'success': False, 'message': 'لا توجد ملفات'}), 400

    sent_ids = []
    for f in files:
        tmp_path = None
        try:
            suffix = _os.path.splitext(f.filename or 'file')[1] or '.bin'
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                f.save(tmp)
                tmp_path = tmp.name

            def _send(tmp=tmp_path, cap=caption):
                async def _inner(client):
                    msg = await client.send_file(
                        entity  = int(chat_id),
                        file    = tmp,
                        caption = cap or None,
                    )
                    return msg.id
                return _inner

            mid = _run_telethon(user_id, _send())
            sent_ids.append(mid)
        except Exception as e:
            logger.error(f'send_media: {e}')
        finally:
            if tmp_path and _os.path.exists(tmp_path):
                try: _os.unlink(tmp_path)
                except Exception: pass

    if sent_ids:
        return jsonify({'success': True, 'message_ids': sent_ids})
    return jsonify({'success': False, 'message': 'فشل الإرسال'}), 500


@app.route('/api/media/<int:chat_id>/<int:message_id>', methods=['GET'])
@auth.login_required
def api_get_media(chat_id, message_id):
    """تحميل وسيط رسالة معينة وإعادته كـ base64"""
    import base64
    import tempfile, os as _os
    user_id = session.get('user_id')
    try:
        async def _dl(client):
            msgs = await client.get_messages(chat_id, ids=message_id)
            if not msgs or not msgs[0] or not msgs[0].media:
                return None
            msg = msgs[0]
            with tempfile.NamedTemporaryFile(delete=False, suffix='.bin') as tmp:
                path = await client.download_media(msg, file=tmp)
            return path

        path = _run_telethon(user_id, _dl)
        if not path or not _os.path.exists(path):
            return jsonify({'success': False, 'message': 'لا يوجد وسيط'}), 404

        with open(path, 'rb') as fp:
            data = base64.b64encode(fp.read()).decode()
        _os.unlink(path)

        # تخمين نوع الوسيط
        ext = path.rsplit('.', 1)[-1].lower() if '.' in path else 'bin'
        mime_map = {'jpg': 'image/jpeg', 'jpeg': 'image/jpeg', 'png': 'image/png',
                    'gif': 'image/gif',  'webp': 'image/webp', 'mp4': 'video/mp4',
                    'mp3': 'audio/mpeg', 'ogg': 'audio/ogg',  'pdf': 'application/pdf'}
        mime = mime_map.get(ext, 'application/octet-stream')
        return jsonify({'success': True, 'data': data, 'mime': mime})
    except Exception as e:
        logger.error(f'api_get_media: {e}')
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/chats/<int:chat_id>/messages/more', methods=['GET'])
@auth.login_required
def api_load_more_messages(chat_id):
    """تحميل رسائل أقدم (infinite scroll)"""
    user_id   = session.get('user_id')
    offset_id = int(request.args.get('offset_id', 0))
    limit     = min(int(request.args.get('limit', 30)), 50)
    try:
        async def _load(client):
            me   = await client.get_me()
            msgs = await client.get_messages(
                entity   = chat_id,
                limit    = limit,
                offset_id= offset_id,
                reverse  = False,
            )
            result = []
            for msg in msgs:
                if not msg or not msg.text:
                    continue
                sender = await msg.get_sender()
                sname  = getattr(sender, 'title', None) or \
                         f"{getattr(sender,'first_name','') or ''} {getattr(sender,'last_name','') or ''}".strip() \
                         if sender else 'مستخدم'
                has_media = msg.media is not None
                result.append({
                    'id':          msg.id,
                    'sender_id':   str(msg.sender_id or ''),
                    'sender_name': sname,
                    'text':        msg.message or '',
                    'timestamp':   int(msg.date.timestamp()) if msg.date else None,
                    'status':      'read',
                    'chat_id':     chat_id,
                    'media':       '📎 وسائط' if has_media else None,
                    'has_media':   has_media,
                    'media_type':  str(type(msg.media).__name__) if has_media else None,
                })
            return result
        msgs = _run_telethon(user_id, _load)
        return jsonify({'success': True, 'messages': msgs, 'has_more': len(msgs) == limit})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


# ══════════════════════════════════════════════════════════════════
#  المرحلة 3: الجلسات النشطة + خصوصية + مزامنة
# ══════════════════════════════════════════════════════════════════

@app.route('/api/auth/sessions', methods=['GET'])
@auth.login_required
def api_get_sessions():
    """قائمة الجلسات النشطة لهذا الحساب"""
    user_id = session.get('user_id')
    try:
        async def _get(client):
            from telethon.tl.functions.account import GetAuthorizationsRequest
            result = await client(GetAuthorizationsRequest())
            sessions = []
            for auth_obj in result.authorizations:
                sessions.append({
                    'hash':          auth_obj.hash,
                    'device':        getattr(auth_obj, 'device_model', 'Unknown'),
                    'platform':      getattr(auth_obj, 'platform', ''),
                    'system':        getattr(auth_obj, 'system_version', ''),
                    'app':           getattr(auth_obj, 'app_name', 'Telegram'),
                    'ip':            getattr(auth_obj, 'ip', ''),
                    'country':       getattr(auth_obj, 'country', ''),
                    'current':       getattr(auth_obj, 'current', False),
                    'date_active':   int(getattr(auth_obj, 'date_active', 0).timestamp())
                                     if hasattr(getattr(auth_obj, 'date_active', None), 'timestamp') else 0,
                    'date_created':  int(getattr(auth_obj, 'date_created', 0).timestamp())
                                     if hasattr(getattr(auth_obj, 'date_created', None), 'timestamp') else 0,
                })
            return sessions
        sessions_list = _run_telethon(user_id, _get)
        return jsonify({'success': True, 'sessions': sessions_list})
    except Exception as e:
        logger.error(f'api_get_sessions: {e}')
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/auth/sessions/revoke', methods=['POST'])
@auth.login_required
def api_revoke_session():
    """إنهاء جلسة نشطة"""
    user_id = session.get('user_id')
    data    = request.get_json(force=True) or {}
    h       = data.get('hash')
    if h is None:
        return jsonify({'success': False, 'message': 'hash مطلوب'}), 400
    try:
        async def _revoke(client):
            from telethon.tl.functions.account import ResetAuthorizationRequest
            await client(ResetAuthorizationRequest(hash=int(h)))
        _run_telethon(user_id, _revoke)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/auth/sessions/revoke-all', methods=['POST'])
@auth.login_required
def api_revoke_all_sessions():
    """إنهاء جميع الجلسات الأخرى"""
    user_id = session.get('user_id')
    try:
        async def _revoke_all(client):
            from telethon.tl.functions.auth import ResetAuthorizationsRequest
            await client(ResetAuthorizationsRequest())
        _run_telethon(user_id, _revoke_all)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/auth/2fa/status', methods=['GET'])
@auth.login_required
def api_2fa_status():
    """حالة التحقق بخطوتين"""
    user_id = session.get('user_id')
    try:
        async def _status(client):
            from telethon.tl.functions.account import GetPasswordRequest
            pwd = await client(GetPasswordRequest())
            return {'has_2fa': pwd.has_password, 'hint': getattr(pwd, 'hint', '')}
        result = _run_telethon(user_id, _status)
        return jsonify({'success': True, **result})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/auth/2fa/enable', methods=['POST'])
@auth.login_required
def api_2fa_enable():
    """تفعيل التحقق بخطوتين"""
    user_id  = session.get('user_id')
    data     = request.get_json(force=True) or {}
    password = data.get('password', '').strip()
    hint     = data.get('hint', 'كلمة مرور')
    if not password or len(password) < 6:
        return jsonify({'success': False, 'message': 'كلمة المرور يجب أن تكون 6 أحرف على الأقل'}), 400
    try:
        async def _enable(client):
            await client.edit_2fa(new_password=password, hint=hint)
        _run_telethon(user_id, _enable)
        return jsonify({'success': True, 'message': 'تم تفعيل التحقق بخطوتين'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/auth/2fa/disable', methods=['POST'])
@auth.login_required
def api_2fa_disable():
    """تعطيل التحقق بخطوتين"""
    user_id  = session.get('user_id')
    data     = request.get_json(force=True) or {}
    password = data.get('current_password', '').strip()
    if not password:
        return jsonify({'success': False, 'message': 'كلمة المرور الحالية مطلوبة'}), 400
    try:
        async def _disable(client):
            await client.edit_2fa(current_password=password, new_password='')
        _run_telethon(user_id, _disable)
        return jsonify({'success': True, 'message': 'تم تعطيل التحقق بخطوتين'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/sync/github', methods=['POST'])
@auth.login_required
def api_sync_github():
    """مزامنة يدوية مع GitHub"""
    user_id = session.get('user_id')
    try:
        import threading
        def _backup():
            db.backup_to_github(user_id)
        threading.Thread(target=_backup, daemon=True).start()
        return jsonify({'success': True, 'message': 'بدأت المزامنة في الخلفية'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/privacy/settings', methods=['GET'])
@auth.login_required
def api_privacy_get():
    """إعدادات الخصوصية المحفوظة"""
    user_id  = session.get('user_id')
    settings = db.get_all_settings(user_id)
    privacy  = {k: v for k, v in settings.items() if k.startswith('privacy_')}
    return jsonify({'success': True, 'privacy': privacy})


@app.route('/api/sync/export', methods=['GET'])
@auth.login_required
def api_sync_export():
    """تصدير كل بيانات المستخدم"""
    user_id = session.get('user_id')
    data    = db.export_user_data(user_id)
    data['exported_at'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    data['user_id']     = user_id
    return jsonify({'success': True, 'data': data})


@app.route('/api/sync/import', methods=['POST'])
@auth.login_required
def api_sync_import():
    """استيراد بيانات المزامنة"""
    user_id = session.get('user_id')
    data    = request.get_json(force=True) or {}
    payload = data.get('data', data)
    count   = db.import_user_data(user_id, payload)
    # مزامنة فورية مع GitHub
    import threading
    threading.Thread(target=db.backup_to_github, args=(user_id,), daemon=True).start()
    return jsonify({'success': True, 'imported': count})


@app.route('/api/sync/status', methods=['GET'])
@auth.login_required
def api_sync_status():
    """حالة المزامنة الأخيرة"""
    user_id = session.get('user_id')
    last_sync = db.get_setting(user_id, 'last_sync_time') or 'لم تتم مزامنة'
    return jsonify({'success': True, 'last_sync': last_sync, 'user_id': user_id})


@app.route('/api/privacy/settings', methods=['POST'])
@auth.login_required
def api_privacy_update():
    """حفظ إعداد خصوصية"""
    user_id = session.get('user_id')
    data    = request.get_json(force=True) or {}
    key     = (data.get('key') or '').strip()
    value   = data.get('value')
    if not key.startswith('privacy_'):
        key = 'privacy_' + key
    db.set_setting(user_id, key, value)
    return jsonify({'success': True})


# ══════════════════════════════════════════════════════════════════
#  المرحلة 6: سجل المكالمات + إشارات WebRTC
# ══════════════════════════════════════════════════════════════════

@app.route('/api/calls/log', methods=['POST'])
@auth.login_required
def api_log_call():
    """تسجيل مكالمة في السجل"""
    user_id = session.get('user_id')
    data    = request.get_json(force=True) or {}
    with db.get_connection() as conn:
        conn.execute('''
            INSERT INTO call_history (user_id, peer_id, peer_name, direction, status, duration, ended_at)
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ''', (
            user_id,
            str(data.get('peer_id', '')),
            data.get('peer_name', 'مستخدم'),
            data.get('direction', 'outgoing'),
            data.get('status', 'ended'),
            int(data.get('duration', 0)),
        ))
    return jsonify({'success': True})


@app.route('/api/calls/history', methods=['GET'])
@auth.login_required
def api_call_history():
    """سجل المكالمات"""
    user_id = session.get('user_id')
    limit   = min(int(request.args.get('limit', 50)), 100)
    with db.get_connection() as conn:
        rows = conn.execute('''
            SELECT * FROM call_history WHERE user_id=?
            ORDER BY started_at DESC LIMIT ?
        ''', (user_id, limit)).fetchall()
    return jsonify({'success': True, 'calls': [dict(r) for r in rows]})


# ══════════════════════════════════════════════════════════════════
#  إشارات المكالمات الصوتية (Socket.IO WebRTC)
# ══════════════════════════════════════════════════════════════════

@socketio.on('call_offer')
def on_call_offer(data):
    """إعادة إرسال العرض للمستخدم المستهدف"""
    to_user = str(data.get('to_user_id', ''))
    socketio.emit('incoming_call', {
        'from_user_id': data.get('from_user_id'),
        'from_name':    data.get('from_name', 'مستخدم'),
        'offer':        data.get('offer'),
    }, room=f'user_{to_user}')


@socketio.on('call_answer')
def on_call_answer(data):
    """إعادة إرسال الإجابة للمتصل"""
    to_user = str(data.get('to_user_id', ''))
    socketio.emit('call_answered', {
        'answer': data.get('answer'),
    }, room=f'user_{to_user}')


@socketio.on('call_ice')
def on_call_ice(data):
    """تبادل مرشحات ICE"""
    to_user = str(data.get('to_user_id', ''))
    socketio.emit('call_ice', {
        'candidate': data.get('candidate'),
    }, room=f'user_{to_user}')


@socketio.on('call_end')
def on_call_end(data):
    """إنهاء المكالمة"""
    to_user = str(data.get('to_user_id', ''))
    socketio.emit('call_ended', {}, room=f'user_{to_user}')


@socketio.on('call_reject')
def on_call_reject(data):
    """رفض المكالمة"""
    to_user = str(data.get('to_user_id', ''))
    socketio.emit('call_rejected', {}, room=f'user_{to_user}')


@socketio.on('call_busy')
def on_call_busy(data):
    """المستخدم مشغول"""
    to_user = str(data.get('to_user_id', ''))
    socketio.emit('call_busy', {}, room=f'user_{to_user}')


# ══════════════════════════════════════════════════════════════════
#  معالجة الأخطاء
# ══════════════════════════════════════════════════════════════════

@app.errorhandler(404)
def not_found(e):
    return jsonify({'success': False, 'message': 'الصفحة غير موجودة'}), 404


@app.errorhandler(500)
def server_error(e):
    logger.error(f"Internal error: {e}")
    return jsonify({'success': False, 'message': 'خطأ داخلي في الخادم'}), 500


# ══════════════════════════════════════════════════════════════════
#  تشغيل التطبيق
# ══════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    logger.info(f"🚀 تشغيل مركز سرعة إنجاز — المرحلة 2")
    logger.info(f"📦 قاعدة البيانات: {Config.DATABASE}")
    logger.info(f"🔗 المستودع: {Config.GITHUB_REPO}")
    socketio.run(
        app,
        host=Config.SOCKET_HOST,
        port=Config.SOCKET_PORT,
        debug=Config.DEBUG,
        allow_unsafe_werkzeug=True,
    )
