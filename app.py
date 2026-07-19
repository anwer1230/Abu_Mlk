"""
app.py — مركز سرعة إنجاز
╔══════════════════════════════════════════════════════════════════╗
║   التطبيق الرئيسي — Flask + SocketIO — المراحل 1-15 المتكاملة   ║
║   المستودع الأصلي: https://github.com/anwer1230/Abu_Mlk          ║
╚══════════════════════════════════════════════════════════════════╝
"""

import os
import time
import logging
import threading

from flask import (
    Flask, render_template, request, jsonify,
    session, redirect, url_for, send_from_directory
)
from flask_socketio import SocketIO, emit, join_room, leave_room

from config import Config
from database import Database, get_db
from auth import AuthManager
from upload_handler import UploadHandler
from bot_manager import BotManager

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
)
logger = logging.getLogger(__name__)

Config.ensure_dirs()

app = Flask(__name__)
app.config['SECRET_KEY']              = Config.SECRET_KEY
app.config['DEBUG']                   = Config.DEBUG
app.config['MAX_CONTENT_LENGTH']      = Config.MAX_FILE_SIZE
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE']   = False

socketio = SocketIO(
    app,
    cors_allowed_origins='*',
    async_mode='threading',
    logger=False,
    engineio_logger=False,
)

db          = get_db()
auth        = AuthManager(db)
upload_handler = UploadHandler(app, db)
bot_manager = BotManager(db)
bot_manager.init_app()

active_sessions: dict = {}   # {user_id: {'sid': sid, 'rooms': []}}
typing_timers:  dict = {}    # {chat_id: {user_id: Timer}}


# ══════════════════════════════════════════════════════════════════
#  الصفحات الرئيسية
# ══════════════════════════════════════════════════════════════════

@app.route('/')
def index():
    if auth.is_authenticated():
        return render_template(
            'index.html',
            user_id=session.get('user_id'),
            user_name=session.get('user_name'),
        )
    return redirect(url_for('login_page'))


@app.route('/login')
def login_page():
    if auth.is_authenticated():
        return redirect(url_for('index'))
    return render_template('login.html')


# ══════════════════════════════════════════════════════════════════
#  مسارات المصادقة
# ══════════════════════════════════════════════════════════════════

@app.route('/api/auth/send-code', methods=['POST'])
def api_send_code():
    data  = request.get_json(force=True) or {}
    phone = (data.get('phone') or '').strip()
    if not phone:
        return jsonify({'success': False, 'message': 'رقم الهاتف مطلوب'}), 400
    db.log_activity(None, 'send_code', f'phone={phone}', request.remote_addr)
    result = auth.send_code(phone)
    return jsonify(result)


@app.route('/api/auth/check-code', methods=['POST'])
def api_check_code():
    data  = request.get_json(force=True) or {}
    phone = (data.get('phone') or '').strip()
    code  = (data.get('code')  or '').strip()
    if not phone or not code:
        return jsonify({'success': False, 'message': 'بيانات ناقصة'}), 400
    result = auth.check_code(phone, code)
    if result.get('success'):
        logged_user_id = session.get('user_id')
        db.log_activity(logged_user_id, 'login_success', f'phone={phone}', request.remote_addr)
        if logged_user_id:
            threading.Thread(
                target=db.backup_to_github, args=(logged_user_id,), daemon=True
            ).start()
    return jsonify(result)


@app.route('/api/auth/check-password', methods=['POST'])
def api_check_password():
    data     = request.get_json(force=True) or {}
    phone    = (data.get('phone') or '').strip()
    password = (data.get('password') or '').strip()
    if not phone or not password:
        return jsonify({'success': False, 'message': 'بيانات ناقصة'}), 400
    result = auth.check_password(phone, password)
    return jsonify(result)


@app.route('/api/auth/logout', methods=['POST'])
def api_logout():
    user_id = session.get('user_id')
    db.log_activity(user_id, 'logout', '', request.remote_addr)
    session.clear()
    return jsonify({'success': True})


@app.route('/api/auth/status', methods=['GET'])
def api_auth_status():
    if auth.is_authenticated():
        return jsonify({
            'authenticated': True,
            'user_id':   session.get('user_id'),
            'user_name': session.get('user_name'),
        })
    return jsonify({'authenticated': False})


@app.route('/api/user/info')
@auth.login_required
def api_user_info():
    user_id = session.get('user_id')
    info = auth.get_user_info(user_id) or {}
    return jsonify({'success': True, 'user': info})


@app.route('/api/users')
@auth.login_required
def api_get_users():
    user_id = session.get('user_id')
    try:
        async def _get(client):
            dialogs = await client.get_dialogs(limit=100)
            result  = []
            for d in dialogs:
                e = d.entity
                uid = getattr(e, 'id', None)
                if uid:
                    result.append({
                        'id':       uid,
                        'name':     getattr(e, 'title', None) or
                                    f"{getattr(e,'first_name','') or ''} {getattr(e,'last_name','') or ''}".strip(),
                        'username': getattr(e, 'username', None),
                        'is_online': getattr(getattr(e, 'status', None), 'expires', None) is not None,
                    })
            return result
        users = _run_telethon(user_id, _get)
        return jsonify({'success': True, 'users': users})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


# ══════════════════════════════════════════════════════════════════
#  أحداث Socket.IO
# ══════════════════════════════════════════════════════════════════

def _stop_typing(chat_id, user_id):
    socketio.emit('user_typing', {
        'user_id': user_id, 'chat_id': chat_id, 'is_typing': False,
    }, room=f'chat_{chat_id}')


@socketio.on('connect')
def handle_connect():
    logger.debug(f'Socket connect: {request.sid}')


@socketio.on('disconnect')
def handle_disconnect():
    for uid, info in list(active_sessions.items()):
        if info.get('sid') == request.sid:
            del active_sessions[uid]
            socketio.emit('user_offline', {'user_id': uid})
            break


@socketio.on('register_user')
def handle_register(data):
    user_id = str(data.get('user_id', ''))
    if not user_id:
        return
    active_sessions[user_id] = {'sid': request.sid, 'rooms': []}
    join_room(f'user_{user_id}')
    socketio.emit('user_online', {'user_id': user_id})


@socketio.on('join_chat')
def handle_join_chat(data):
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
    user_id = data.get('user_id')
    chat_id = data.get('chat_id')
    if not user_id or not chat_id:
        return
    room = f'chat_{chat_id}'
    leave_room(room)
    if user_id in active_sessions and room in active_sessions[user_id]['rooms']:
        active_sessions[user_id]['rooms'].remove(room)


@socketio.on('send_message')
def handle_send_message(data):
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
        'id':          message_id,
        'sender_id':   user_id,
        'sender_name': user_name,
        'chat_id':     chat_id,
        'text':        text,
        'timestamp':   int(time.time()),
        'status':      'sent',
        'reply_to':    reply_to,
    }
    socketio.emit('new_message', msg_obj, room=f'chat_{chat_id}')
    emit('message_sent', {'message_id': message_id, 'status': 'delivered'}, to=request.sid)
    def _bg():
        try:
            _run_telethon(user_id, lambda c: c.send_message(int(chat_id), text, reply_to=reply_to))
        except Exception as ex:
            logger.warning(f'send_message Telethon: {ex}')
    threading.Thread(target=_bg, daemon=True).start()


@socketio.on('mark_as_read')
def handle_mark_as_read(data):
    user_id = data.get('user_id')
    chat_id = data.get('chat_id')
    if not user_id or not chat_id:
        return
    socketio.emit('messages_read', {'chat_id': chat_id, 'reader_id': user_id},
                  room=f'chat_{chat_id}')


@socketio.on('typing_start')
def handle_typing_start(data):
    user_id = data.get('user_id')
    chat_id = data.get('chat_id')
    if not user_id or not chat_id:
        return
    if chat_id in typing_timers and user_id in typing_timers[chat_id]:
        typing_timers[chat_id][user_id].cancel()
    emit('user_typing', {'user_id': user_id, 'chat_id': chat_id, 'is_typing': True},
         room=f'chat_{chat_id}', skip_sid=request.sid)
    t = threading.Timer(3.0, _stop_typing, args=(chat_id, user_id))
    t.daemon = True
    t.start()
    typing_timers.setdefault(chat_id, {})[user_id] = t


@socketio.on('typing_stop')
def handle_typing_stop(data):
    user_id = data.get('user_id')
    chat_id = data.get('chat_id')
    if not user_id or not chat_id:
        return
    if chat_id in typing_timers and user_id in typing_timers[chat_id]:
        typing_timers[chat_id][user_id].cancel()
        del typing_timers[chat_id][user_id]
    emit('user_typing', {'user_id': user_id, 'chat_id': chat_id, 'is_typing': False},
         room=f'chat_{chat_id}')


@socketio.on('delete_message')
def handle_delete_message(data):
    user_id    = data.get('user_id')
    chat_id    = data.get('chat_id')
    message_id = data.get('message_id')
    if not user_id or not chat_id or not message_id:
        return
    socketio.emit('message_deleted', {'chat_id': chat_id, 'message_id': message_id},
                  room=f'chat_{chat_id}')
    def _bg():
        try:
            _run_telethon(user_id, lambda c: c.delete_messages(int(chat_id), [int(message_id)]))
        except Exception as ex:
            logger.warning(f'delete_message: {ex}')
    threading.Thread(target=_bg, daemon=True).start()


@socketio.on('edit_message')
def handle_edit_message(data):
    user_id    = data.get('user_id')
    chat_id    = data.get('chat_id')
    message_id = data.get('message_id')
    new_text   = (data.get('new_text') or '').strip()
    if not user_id or not chat_id or not message_id or not new_text:
        return
    socketio.emit('message_edited', {
        'chat_id': chat_id, 'message_id': message_id, 'new_text': new_text,
        'edited_at': int(time.time()),
    }, room=f'chat_{chat_id}')
    def _bg():
        try:
            _run_telethon(user_id, lambda c: c.edit_message(int(chat_id), int(message_id), new_text))
        except Exception as ex:
            logger.warning(f'edit_message: {ex}')
    threading.Thread(target=_bg, daemon=True).start()


@socketio.on('get_online_status')
def handle_get_online_status(data):
    target = str(data.get('user_id', ''))
    is_online = target in active_sessions
    emit('online_status', {'user_id': target, 'is_online': is_online}, to=request.sid)


@socketio.on('get_chat_participants')
def handle_get_chat_participants(data):
    chat_id = str(data.get('chat_id', ''))
    if not chat_id:
        return
    participants = [
        uid for uid, info in active_sessions.items()
        if f'chat_{chat_id}' in info.get('rooms', [])
    ]
    emit('chat_participants', {'chat_id': chat_id, 'participants': participants}, to=request.sid)


# ══════════════════════════════════════════════════════════════════
#  أحداث Socket.IO — المكالمات الصوتية (WebRTC) — المرحلة 14
# ══════════════════════════════════════════════════════════════════

@socketio.on('call_offer')
def on_call_offer(data):
    to_user = str(data.get('to_user_id', ''))
    socketio.emit('incoming_call', {
        'from_user_id': data.get('from_user_id'),
        'from_name':    data.get('from_name', 'مستخدم'),
        'offer':        data.get('offer'),
    }, room=f'user_{to_user}')


@socketio.on('call_answer')
def on_call_answer(data):
    to_user = str(data.get('to_user_id', ''))
    socketio.emit('call_answered', {
        'answer': data.get('answer'),
    }, room=f'user_{to_user}')


@socketio.on('call_ice')
def on_call_ice(data):
    to_user = str(data.get('to_user_id', ''))
    socketio.emit('call_ice', {
        'candidate': data.get('candidate'),
    }, room=f'user_{to_user}')


@socketio.on('call_end')
def on_call_end(data):
    to_user = str(data.get('to_user_id', ''))
    socketio.emit('call_ended', {}, room=f'user_{to_user}')
    # تسجيل المكالمة في السجل
    user_id = session.get('user_id')
    if user_id and to_user:
        try:
            with db.get_connection() as conn:
                conn.execute('''
                    INSERT OR IGNORE INTO call_history
                    (user_id, peer_id, peer_name, direction, status, duration)
                    VALUES (?, ?, ?, 'outgoing', 'ended', 0)
                ''', (user_id, to_user, 'مستخدم'))
        except Exception:
            pass


@socketio.on('call_reject')
def on_call_reject(data):
    to_user = str(data.get('to_user_id', ''))
    socketio.emit('call_rejected', {}, room=f'user_{to_user}')


@socketio.on('call_busy')
def on_call_busy(data):
    to_user = str(data.get('to_user_id', ''))
    socketio.emit('call_busy', {}, room=f'user_{to_user}')


# ══════════════════════════════════════════════════════════════════
#  مساعد Telethon
# ══════════════════════════════════════════════════════════════════

def _run_telethon(user_id: str, coro):
    """تشغيل coroutine Telethon في thread جديد بـ event loop مستقل."""
    import asyncio
    result_box = [None]
    error_box  = [None]

    def _worker():
        import asyncio as _asyncio
        loop = _asyncio.new_event_loop()
        _asyncio.set_event_loop(loop)
        try:
            from telethon import TelegramClient
            session_file = os.path.join(Config.SESSION_DIR, str(user_id))
            client = TelegramClient(session_file, Config.TDLIB_API_ID, Config.TDLIB_API_HASH)

            async def _run():
                await client.connect()
                if not await client.is_user_authorized():
                    raise RuntimeError('غير مصادق عليه')
                result_box[0] = await coro(client)
                await client.disconnect()

            loop.run_until_complete(_run())
        except Exception as ex:
            error_box[0] = ex
        finally:
            loop.close()

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    t.join(timeout=25)
    if error_box[0]:
        raise error_box[0]
    return result_box[0]


# ══════════════════════════════════════════════════════════════════
#  مسارات المحادثات والرسائل
# ══════════════════════════════════════════════════════════════════

@app.route('/api/chats', methods=['GET'])
@auth.login_required
def get_chats():
    user_id = session.get('user_id')
    limit   = min(int(request.args.get('limit', 50)), 100)
    try:
        async def _fetch(client):
            dialogs = await client.get_dialogs(limit=limit)
            result  = []
            for d in dialogs:
                e = d.entity
                msg = d.message
                result.append({
                    'id':           d.id,
                    'name':         d.name or 'محادثة',
                    'is_group':     d.is_group,
                    'is_channel':   d.is_channel,
                    'unread_count': d.unread_count,
                    'last_message': {
                        'text':      getattr(msg, 'message', '') or '',
                        'timestamp': int(msg.date.timestamp()) if msg and msg.date else None,
                        'from_me':   getattr(msg, 'out', False),
                    } if msg else None,
                    'pinned':  d.pinned,
                    'archived': d.archived,
                })
            return result
        chats = _run_telethon(user_id, _fetch)
        return jsonify({'success': True, 'chats': chats})
    except Exception as e:
        logger.error(f'get_chats: {e}')
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/chats/<int:chat_id>/messages', methods=['GET'])
@auth.login_required
def get_chat_messages(chat_id):
    user_id   = session.get('user_id')
    limit     = min(int(request.args.get('limit', 50)), 100)
    offset_id = int(request.args.get('offset_id', 0))
    try:
        async def _fetch(client):
            msgs = await client.get_messages(chat_id, limit=limit, offset_id=offset_id)
            me   = await client.get_me()
            result = []
            for msg in msgs:
                sender = await msg.get_sender()
                sname  = getattr(sender, 'title', None) or \
                         f"{getattr(sender,'first_name','') or ''} {getattr(sender,'last_name','') or ''}".strip() \
                         if sender else 'مستخدم'
                result.append({
                    'id':          msg.id,
                    'chat_id':     chat_id,
                    'sender_id':   msg.sender_id,
                    'sender_name': sname,
                    'text':        msg.message or '',
                    'timestamp':   int(msg.date.timestamp()) if msg.date else None,
                    'from_me':     msg.sender_id == me.id,
                    'edited':      msg.edit_date is not None,
                    'reply_to':    getattr(msg.reply_to, 'reply_to_msg_id', None),
                    'has_media':   msg.media is not None,
                })
            return result
        messages = _run_telethon(user_id, _fetch)
        return jsonify({'success': True, 'messages': messages})
    except Exception as e:
        logger.error(f'get_chat_messages: {e}')
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/messages/send', methods=['POST'])
@auth.login_required
def api_send_message():
    user_id = session.get('user_id')
    data    = request.get_json(force=True) or {}
    chat_id = data.get('chat_id')
    text    = (data.get('text') or '').strip()
    reply_to = data.get('reply_to')
    if not chat_id or not text:
        return jsonify({'success': False, 'message': 'بيانات ناقصة'}), 400
    try:
        async def _send(client):
            msg = await client.send_message(int(chat_id), text, reply_to=reply_to)
            return {'id': msg.id, 'timestamp': int(msg.date.timestamp())}
        result = _run_telethon(user_id, _send)
        return jsonify({'success': True, **result})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


# ══════════════════════════════════════════════════════════════════
#  مسارات المجلدات المشتركة
# ══════════════════════════════════════════════════════════════════

def _folder_member(conn, folder_id, user_id, min_level=1):
    row = conn.execute(
        'SELECT permission_level FROM folder_members WHERE folder_id=? AND user_id=?',
        (folder_id, user_id)
    ).fetchone()
    return row and row['permission_level'] >= min_level


def _notify_folder_members(folder_id, event_name, data):
    with db.get_connection() as conn:
        members = conn.execute(
            'SELECT user_id FROM folder_members WHERE folder_id=?', (folder_id,)
        ).fetchall()
    for m in members:
        uid = m['user_id']
        if uid in active_sessions:
            socketio.emit(event_name, data, room=f'user_{uid}')


@app.route('/api/folders', methods=['GET'])
@auth.login_required
def get_folders():
    user_id = session.get('user_id')
    with db.get_connection() as conn:
        folders = conn.execute('''
            SELECT sf.*, fm.permission_level
            FROM shared_folders sf
            JOIN folder_members fm ON sf.id = fm.folder_id
            WHERE fm.user_id = ? AND sf.is_active = 1
        ''', (user_id,)).fetchall()
    result = []
    for f in folders:
        f = dict(f)
        with db.get_connection() as conn:
            f['chats'] = [dict(r) for r in conn.execute(
                'SELECT * FROM folder_chats WHERE folder_id=?', (f['id'],)
            ).fetchall()]
            f['member_count'] = conn.execute(
                'SELECT COUNT(*) FROM folder_members WHERE folder_id=?', (f['id'],)
            ).fetchone()[0]
        result.append(f)
    return jsonify({'success': True, 'folders': result})


@app.route('/api/folders', methods=['POST'])
@auth.login_required
def create_folder():
    user_id = session.get('user_id')
    data    = request.get_json(force=True) or {}
    name    = (data.get('name') or '').strip()
    icon    = data.get('icon', '📁')
    if not name:
        return jsonify({'success': False, 'message': 'اسم المجلد مطلوب'}), 400
    with db.get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            'INSERT INTO shared_folders (name, icon, owner_id) VALUES (?, ?, ?)',
            (name, icon, user_id)
        )
        folder_id = cur.lastrowid
        conn.execute(
            'INSERT INTO folder_members (folder_id, user_id, permission_level) VALUES (?, ?, 3)',
            (folder_id, user_id)
        )
    threading.Thread(target=db.backup_to_github, args=(user_id,), daemon=True).start()
    return jsonify({'success': True, 'folder_id': folder_id, 'name': name})


@app.route('/api/folders/<int:folder_id>', methods=['DELETE'])
@auth.login_required
def delete_folder(folder_id):
    user_id = session.get('user_id')
    with db.get_connection() as conn:
        if not _folder_member(conn, folder_id, user_id, min_level=3):
            return jsonify({'success': False, 'message': 'غير مصرح'}), 403
        conn.execute('UPDATE shared_folders SET is_active=0 WHERE id=?', (folder_id,))
    _notify_folder_members(folder_id, 'folder_deleted', {'folder_id': folder_id})
    return jsonify({'success': True})


@app.route('/api/folders/<int:folder_id>/members', methods=['POST'])
@auth.login_required
def add_folder_member(folder_id):
    user_id       = session.get('user_id')
    data          = request.get_json(force=True) or {}
    new_member_id = str(data.get('user_id', ''))
    permission    = int(data.get('permission_level', 1))
    if not new_member_id:
        return jsonify({'success': False, 'message': 'معرف المستخدم مطلوب'}), 400
    with db.get_connection() as conn:
        if not _folder_member(conn, folder_id, user_id, min_level=2):
            return jsonify({'success': False, 'message': 'غير مصرح'}), 403
        conn.execute('''
            INSERT OR REPLACE INTO folder_members (folder_id, user_id, permission_level)
            VALUES (?, ?, ?)
        ''', (folder_id, new_member_id, permission))
    _notify_folder_members(folder_id, 'folder_member_added', {
        'folder_id': folder_id, 'user_id': new_member_id
    })
    return jsonify({'success': True})


# ══════════════════════════════════════════════════════════════════
#  مسارات البوتات
# ══════════════════════════════════════════════════════════════════

@app.route('/api/bots', methods=['GET'])
@auth.login_required
def api_get_bots():
    bots = bot_manager.list_bots()
    return jsonify({'success': True, 'bots': bots})


@app.route('/api/bots', methods=['POST'])
@auth.login_required
def api_create_bot():
    user_id  = session.get('user_id')
    data     = request.get_json(force=True) or {}
    name     = (data.get('name') or '').strip()
    phone    = (data.get('phone') or '').strip()
    api_id   = data.get('api_id') or Config.TDLIB_API_ID
    api_hash = data.get('api_hash') or Config.TDLIB_API_HASH
    if not name:
        return jsonify({'success': False, 'message': 'اسم البوت مطلوب'}), 400
    bot_id = bot_manager.register_bot(name, phone=phone, api_id=str(api_id),
                                      api_hash=api_hash, user_id=user_id)
    return jsonify({'success': True, 'bot_id': bot_id, 'name': name})


@app.route('/api/bots/<bot_name>', methods=['DELETE'])
@auth.login_required
def api_delete_bot(bot_name):
    with db.get_connection() as conn:
        conn.execute('UPDATE bots SET is_active=0 WHERE name=?', (bot_name,))
    return jsonify({'success': True})


@app.route('/api/bots/<bot_name>/commands', methods=['GET'])
@auth.login_required
def api_bot_commands(bot_name):
    with db.get_connection() as conn:
        row = conn.execute('SELECT id FROM bots WHERE name=?', (bot_name,)).fetchone()
        if not row:
            return jsonify({'success': False, 'message': 'البوت غير موجود'}), 404
        cmds = conn.execute(
            'SELECT * FROM bot_commands WHERE bot_id=? AND is_active=1', (row['id'],)
        ).fetchall()
    return jsonify({'success': True, 'commands': [dict(c) for c in cmds]})


@app.route('/api/bots/<bot_name>/message', methods=['POST'])
@auth.login_required
def api_bot_message(bot_name):
    data    = request.get_json(force=True) or {}
    text    = (data.get('text') or '').strip()
    chat_id = data.get('chat_id')
    if not text or not chat_id:
        return jsonify({'success': False, 'message': 'بيانات ناقصة'}), 400
    bot = bot_manager.get_bot(bot_name)
    if not bot:
        return jsonify({'success': False, 'message': 'البوت غير موجود'}), 404
    return jsonify({'success': True, 'message': 'تم الإرسال'})


# ══════════════════════════════════════════════════════════════════
#  تفاعلات الرسائل + البحث + الملف الشخصي
# ══════════════════════════════════════════════════════════════════

@app.route('/api/messages/reaction', methods=['POST'])
@auth.login_required
def api_msg_reaction():
    user_id    = session.get('user_id')
    data       = request.get_json(force=True) or {}
    chat_id    = int(data.get('chat_id', 0))
    message_id = int(data.get('message_id', 0))
    reaction   = data.get('reaction', '👍')
    if not chat_id or not message_id:
        return jsonify({'success': False, 'message': 'بيانات ناقصة'}), 400
    with db.get_connection() as conn:
        conn.execute('''
            INSERT OR REPLACE INTO message_reactions (user_id, chat_id, message_id, reaction)
            VALUES (?, ?, ?, ?)
        ''', (user_id, str(chat_id), str(message_id), reaction))
    socketio.emit('reaction_added', {
        'chat_id': chat_id, 'message_id': message_id,
        'user_id': user_id, 'reaction': reaction,
    }, room=f'chat_{chat_id}')
    return jsonify({'success': True})


@app.route('/api/messages/reactions', methods=['GET'])
@auth.login_required
def api_get_reactions():
    chat_id    = request.args.get('chat_id')
    message_id = request.args.get('message_id')
    if not chat_id or not message_id:
        return jsonify({'success': False}), 400
    with db.get_connection() as conn:
        rows = conn.execute('''
            SELECT reaction, COUNT(*) as count
            FROM message_reactions
            WHERE chat_id=? AND message_id=?
            GROUP BY reaction
        ''', (str(chat_id), str(message_id))).fetchall()
    return jsonify({'success': True, 'reactions': [dict(r) for r in rows]})


@app.route('/api/messages/forward', methods=['POST'])
@auth.login_required
def api_forward_messages():
    user_id = session.get('user_id')
    data    = request.get_json(force=True) or {}
    from_id = data.get('from_chat_id')
    to_id   = data.get('to_chat_id')
    msg_ids = data.get('message_ids', [])
    if not from_id or not to_id or not msg_ids:
        return jsonify({'success': False, 'message': 'بيانات ناقصة'}), 400
    try:
        async def _fwd(client):
            await client.forward_messages(int(to_id), msg_ids, int(from_id))
        _run_telethon(user_id, _fwd)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/messages/pin', methods=['POST'])
@auth.login_required
def api_pin_message():
    user_id    = session.get('user_id')
    data       = request.get_json(force=True) or {}
    chat_id    = data.get('chat_id')
    message_id = data.get('message_id')
    if not chat_id or not message_id:
        return jsonify({'success': False}), 400
    try:
        async def _pin(client):
            from telethon.tl.functions.messages import UpdatePinnedMessageRequest
            await client(UpdatePinnedMessageRequest(
                peer=int(chat_id), id=int(message_id), silent=True
            ))
        _run_telethon(user_id, _pin)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/messages/bookmark', methods=['POST'])
@auth.login_required
def api_bookmark_message():
    user_id    = session.get('user_id')
    data       = request.get_json(force=True) or {}
    chat_id    = str(data.get('chat_id', ''))
    message_id = str(data.get('message_id', ''))
    text       = data.get('text', '')
    if not chat_id or not message_id:
        return jsonify({'success': False}), 400
    with db.get_connection() as conn:
        conn.execute('''
            INSERT OR IGNORE INTO bookmarks (user_id, chat_id, message_id, text)
            VALUES (?, ?, ?, ?)
        ''', (user_id, chat_id, message_id, text))
    return jsonify({'success': True})


@app.route('/api/messages/bookmarks', methods=['GET'])
@auth.login_required
def api_get_bookmarks():
    user_id = session.get('user_id')
    with db.get_connection() as conn:
        rows = conn.execute(
            'SELECT * FROM bookmarks WHERE user_id=? ORDER BY created_at DESC', (user_id,)
        ).fetchall()
    return jsonify({'success': True, 'bookmarks': [dict(r) for r in rows]})


@app.route('/api/chats/<int:chat_id>/archive', methods=['POST'])
@auth.login_required
def api_archive_chat(chat_id):
    user_id = session.get('user_id')
    data    = request.get_json(force=True) or {}
    archive = data.get('archived', True)
    db.set_setting(user_id, f'chat_archived_{chat_id}', archive)
    return jsonify({'success': True, 'archived': archive})


@app.route('/api/chats/<int:chat_id>/mute', methods=['POST'])
@auth.login_required
def api_mute_chat(chat_id):
    user_id = session.get('user_id')
    data    = request.get_json(force=True) or {}
    muted   = data.get('muted', True)
    until   = data.get('until', 0)
    with db.get_connection() as conn:
        conn.execute('''
            INSERT OR REPLACE INTO muted_chats (user_id, chat_id, muted_until)
            VALUES (?, ?, ?)
        ''', (user_id, str(chat_id), until))
    return jsonify({'success': True, 'muted': muted})


@app.route('/api/chats/states', methods=['GET'])
@auth.login_required
def api_chat_states():
    user_id = session.get('user_id')
    settings = db.get_all_settings(user_id)
    archived = {k.replace('chat_archived_', ''): v
                for k, v in settings.items() if k.startswith('chat_archived_')}
    return jsonify({'success': True, 'archived': archived})


# ══════════════════════════════════════════════════════════════════
#  المرحلة 11: حظر المستخدمين + إعدادات الخصوصية المتقدمة
# ══════════════════════════════════════════════════════════════════

@app.route('/privacy')
@auth.login_required
def page_privacy():
    """صفحة الخصوصية المتقدمة — المرحلة 11"""
    return render_template('privacy_settings.html')


@app.route('/api/users/<int:target_user_id>/block', methods=['POST', 'DELETE'])
@auth.login_required
def api_block_user(target_user_id):
    user_id  = session.get('user_id')
    is_block = request.method == 'POST'
    with db.get_connection() as conn:
        if is_block:
            conn.execute(
                'INSERT OR IGNORE INTO blocked_users (user_id, blocked_user_id) VALUES (?, ?)',
                (user_id, str(target_user_id))
            )
        else:
            conn.execute(
                'DELETE FROM blocked_users WHERE user_id=? AND blocked_user_id=?',
                (user_id, str(target_user_id))
            )
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


@app.route('/api/blocked/users', methods=['GET'])
@auth.login_required
def api_list_blocked():
    """قائمة المستخدمين المحظورين — المرحلة 11"""
    user_id = session.get('user_id')
    with db.get_connection() as conn:
        rows = conn.execute('''
            SELECT bu.blocked_user_id, u.name, u.phone, u.username
            FROM blocked_users bu
            LEFT JOIN users u ON bu.blocked_user_id = u.user_id
            WHERE bu.user_id = ?
        ''', (user_id,)).fetchall()
    return jsonify({'success': True, 'users': [dict(r) for r in rows]})


@app.route('/api/privacy/settings', methods=['GET'])
@auth.login_required
def api_privacy_get():
    user_id  = session.get('user_id')
    settings = db.get_all_settings(user_id)
    privacy  = {k: v for k, v in settings.items() if k.startswith('privacy_')}
    return jsonify({'success': True, 'privacy': privacy})


@app.route('/api/privacy/settings', methods=['POST'])
@auth.login_required
def api_privacy_update():
    user_id = session.get('user_id')
    data    = request.get_json(force=True) or {}
    key     = (data.get('key') or data.get('setting') or '').strip()
    value   = data.get('value')
    if not key.startswith('privacy_'):
        key = 'privacy_' + key
    db.set_setting(user_id, key, value)
    threading.Thread(target=db.backup_to_github, args=(user_id,), daemon=True).start()
    return jsonify({'success': True})


# ══════════════════════════════════════════════════════════════════
#  المرحلة 12: المزامنة بين الأجهزة
# ══════════════════════════════════════════════════════════════════

@app.route('/api/sync/github', methods=['POST'])
@auth.login_required
def api_sync_github():
    user_id = session.get('user_id')
    threading.Thread(target=db.backup_to_github, args=(user_id,), daemon=True).start()
    db.set_setting(user_id, 'last_sync_time', time.strftime('%Y-%m-%d %H:%M:%S'))
    return jsonify({'success': True, 'message': 'بدأت المزامنة في الخلفية'})


@app.route('/api/sync/status', methods=['GET'])
@auth.login_required
def api_sync_status():
    user_id   = session.get('user_id')
    last_sync = db.get_setting(user_id, 'last_sync_time') or 'لم تتم مزامنة'
    return jsonify({'success': True, 'last_sync': last_sync, 'user_id': user_id})


@app.route('/api/sync/export', methods=['GET'])
@auth.login_required
def api_sync_export():
    user_id = session.get('user_id')
    data = db.export_user_data(user_id) if hasattr(db, 'export_user_data') else {}
    data['exported_at'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    data['user_id'] = user_id
    return jsonify({'success': True, 'data': data})


@app.route('/api/sync/import', methods=['POST'])
@auth.login_required
def api_sync_import():
    user_id = session.get('user_id')
    data    = request.get_json(force=True) or {}
    payload = data.get('data', data)
    count   = db.import_user_data(user_id, payload) if hasattr(db, 'import_user_data') else 0
    threading.Thread(target=db.backup_to_github, args=(user_id,), daemon=True).start()
    return jsonify({'success': True, 'imported': count})


@app.route('/api/sync/devices', methods=['GET'])
@auth.login_required
def api_sync_devices():
    """قائمة الأجهزة المتصلة — المرحلة 12"""
    user_id = session.get('user_id')
    devices = []
    for uid, info in active_sessions.items():
        if uid == user_id:
            devices.append({
                'id':         info.get('device_id', uid),
                'name':       info.get('device_name', 'جهاز'),
                'type':       info.get('device_type', 'desktop'),
                'is_online':  True,
                'last_active': time.strftime('%H:%M'),
            })
    return jsonify({'success': True, 'devices': devices})


# ══════════════════════════════════════════════════════════════════
#  المرحلة 14: المكالمات الصوتية
# ══════════════════════════════════════════════════════════════════

@app.route('/call/<int:target_user_id>')
@auth.login_required
def voice_call_page(target_user_id):
    """صفحة المكالمة الصوتية المشفرة — المرحلة 14"""
    user = auth.get_user_info(str(target_user_id)) or {}
    return render_template(
        'voice_call.html',
        target_user_id=target_user_id,
        target_name=user.get('name', 'مستخدم'),
    )


@app.route('/api/calls/log', methods=['POST'])
@auth.login_required
def api_log_call():
    user_id = session.get('user_id')
    data    = request.get_json(force=True) or {}
    with db.get_connection() as conn:
        conn.execute('''
            INSERT INTO call_history
            (user_id, peer_id, peer_name, direction, status, duration, ended_at)
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ''', (
            user_id, str(data.get('peer_id', '')), data.get('peer_name', 'مستخدم'),
            data.get('direction', 'outgoing'), data.get('status', 'ended'),
            int(data.get('duration', 0)),
        ))
    return jsonify({'success': True})


@app.route('/api/calls/history', methods=['GET'])
@auth.login_required
def api_call_history():
    user_id = session.get('user_id')
    limit   = min(int(request.args.get('limit', 50)), 100)
    with db.get_connection() as conn:
        rows = conn.execute('''
            SELECT * FROM call_history WHERE user_id=?
            ORDER BY started_at DESC LIMIT ?
        ''', (user_id, limit)).fetchall()
    return jsonify({'success': True, 'calls': [dict(r) for r in rows]})


# ══════════════════════════════════════════════════════════════════
#  البحث + الملف الشخصي + الإعدادات
# ══════════════════════════════════════════════════════════════════

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
            entity  = int(chat_id) if chat_id else 'me'
            msgs    = await client.get_messages(entity, search=q, limit=40)
            me      = await client.get_me()
            results = []
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
            }
        profile = _run_telethon(user_id, _prof)
        return jsonify({'success': True, 'profile': profile})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/settings', methods=['GET'])
@auth.login_required
def api_get_settings():
    user_id  = session.get('user_id')
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
        return jsonify({'success': False, 'message': 'المفتاح مطلوب'}), 400
    db.set_setting(user_id, key, value)
    return jsonify({'success': True})


@app.route('/api/settings/theme', methods=['POST'])
@auth.login_required
def api_set_theme():
    user_id = session.get('user_id')
    data    = request.get_json(force=True) or {}
    theme   = data.get('theme', 'dark')
    if theme not in ('dark', 'light', 'auto'):
        return jsonify({'success': False, 'message': 'سمة غير صالحة'}), 400
    db.set_setting(user_id, 'theme', theme)
    return jsonify({'success': True, 'theme': theme})


@app.route('/api/settings/storage', methods=['GET'])
@auth.login_required
def api_storage_info():
    total_bytes = 0
    for folder in (Config.UPLOAD_DIR, Config.SESSION_DIR):
        if os.path.isdir(folder):
            for dirpath, _, filenames in os.walk(folder):
                for f in filenames:
                    try:
                        total_bytes += os.path.getsize(os.path.join(dirpath, f))
                    except OSError:
                        pass
    return jsonify({
        'success': True,
        'used':    round(total_bytes / (1024 * 1024), 1),
        'total':   1024,
    })


@app.route('/api/settings/clear-cache', methods=['POST'])
@auth.login_required
def api_clear_cache():
    freed = 0
    for d in (os.path.join(Config.UPLOAD_DIR, '.chunks'), getattr(Config, 'TEMP_DIR', '')):
        if d and os.path.isdir(d):
            for f in os.listdir(d):
                fp = os.path.join(d, f)
                try:
                    freed += os.path.getsize(fp)
                    os.remove(fp)
                except OSError:
                    pass
    try:
        from github_db import invalidate_all
        invalidate_all()
    except Exception:
        pass
    freed_mb = round(freed / (1024 * 1024), 1)
    return jsonify({'success': True, 'freed_mb': freed_mb, 'message': f'تم تحرير {freed_mb} MB'})


# ══════════════════════════════════════════════════════════════════
#  صفحات إضافية
# ══════════════════════════════════════════════════════════════════

@app.route('/media_gallery')
@auth.login_required
def page_media_gallery():
    return render_template('media_gallery.html')


@app.route('/security_settings')
@auth.login_required
def page_security_settings():
    return render_template('security_settings.html')


@app.route('/settings_page')
@auth.login_required
def page_settings():
    return render_template('settings.html')


@app.route('/admin')
@auth.login_required
def page_admin():
    return render_template('admin_panel.html')


# ══════════════════════════════════════════════════════════════════
#  معالجة الأخطاء
# ══════════════════════════════════════════════════════════════════

@app.errorhandler(404)
def not_found(e):
    return jsonify({'success': False, 'message': 'الصفحة غير موجودة'}), 404


@app.errorhandler(500)
def server_error(e):
    logger.error(f'Internal error: {e}')
    return jsonify({'success': False, 'message': 'خطأ داخلي في الخادم'}), 500
