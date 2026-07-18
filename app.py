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
        db.log_activity(session.get('user_id'), 'login_success',
                        f'phone={phone}', request.remote_addr)
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
