"""
bot_manager.py — مركز سرعة إنجاز
══════════════════════════════════════════════════════════════
المرحلة 13: نظام البوتات المتقدم
يدعم: أوامر البوت، الأزرار المدمجة، machine-state، معالجات ذكية
المستودع الأصلي: https://github.com/anwer1230/Abu_Mlk
══════════════════════════════════════════════════════════════
"""

import os
import json
import logging
import threading
from typing import Callable, Dict, List, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# ─── نماذج البيانات ───────────────────────────────────────────────

@dataclass
class BotCommand:
    command:     str
    description: str
    handler:     Callable
    admin_only:  bool = False

@dataclass
class BotCallback:
    data:       str
    handler:    Callable
    admin_only: bool = False

@dataclass
class BotState:
    user_id:  int
    chat_id:  int
    state:    str
    data:     dict = field(default_factory=dict)

# ─── الأوامر المدمجة ──────────────────────────────────────────────

BUILTIN_COMMANDS = {
    '/start':  'مرحباً! أنا بوت مركز سرعة إنجاز. اكتب /help لعرض الأوامر.',
    '/help': (
        'الأوامر المتاحة:\n'
        '/start  — الترحيب\n'
        '/help   — قائمة الأوامر\n'
        '/status — حالة الخادم\n'
        '/ping   — اختبار الاتصال\n'
        '/services — الخدمات المتاحة'
    ),
    '/ping':   'Pong! 🏓',
    '/status': 'الخادم يعمل بشكل طبيعي ✅',
    '/services': (
        '📚 الخدمات الأكاديمية\n'
        '💼 الخدمات الإدارية\n'
        '🤖 الذكاء الاصطناعي\n'
        '📞 الدعم الفني\n\n'
        'تواصل معنا: https://wa.me/966510349663'
    ),
}

# ─── القوائم الذكية (Inline keyboards) ───────────────────────────

MAIN_MENU = {
    'text': '👋 مرحباً! اختر الخدمة المناسبة 👇',
    'buttons': [
        [{'text': '📚 أكاديمي', 'data': 'menu_academic'}],
        [{'text': '💼 إداري', 'data': 'menu_admin'}],
        [{'text': '🤖 ذكاء اصطناعي', 'data': 'menu_ai'}],
        [{'text': '📞 دعم فني', 'data': 'menu_support'}],
    ]
}

CALLBACK_MENUS = {
    'menu_academic': {
        'text': '📚 **الخدمات الأكاديمية:**\n\n1. 🔍 البحث العلمي\n2. 📊 التحليل الإحصائي\n3. 📝 تنسيق APA/MLA/IEEE\n4. 🎓 استشارات أكاديمية',
        'buttons': [
            [{'text': '🔍 بحث علمي', 'data': 'svc_research'}],
            [{'text': '📊 تحليل إحصائي', 'data': 'svc_stats'}],
            [{'text': '🔙 رجوع', 'data': 'menu_main'}],
        ]
    },
    'menu_admin': {
        'text': '💼 **الخدمات الإدارية:**\n\n1. 📋 إدارة المهام\n2. 📈 متابعة الإنجاز\n3. 📊 التقارير\n4. 👥 إدارة الفريق',
        'buttons': [
            [{'text': '📋 إدارة المهام', 'data': 'svc_tasks'}],
            [{'text': '📈 متابعة الإنجاز', 'data': 'svc_progress'}],
            [{'text': '🔙 رجوع', 'data': 'menu_main'}],
        ]
    },
    'menu_ai': {
        'text': '🤖 **خدمات الذكاء الاصطناعي:**\n\n1. 📊 تحليل البيانات\n2. 🔮 التنبؤات\n3. 🧠 التعلم الآلي',
        'buttons': [
            [{'text': '📊 تحليل البيانات', 'data': 'svc_data'}],
            [{'text': '🔙 رجوع', 'data': 'menu_main'}],
        ]
    },
    'menu_support': {
        'text': '📞 **التواصل مع الدعم:**\n\n📱 واتساب: +966510349663\n📧 البريد: support@speed-engaz.com',
        'buttons': [
            [{'text': '📱 واتساب', 'url': 'https://wa.me/966510349663'}],
            [{'text': '🔙 رجوع', 'data': 'menu_main'}],
        ]
    },
    'menu_main': MAIN_MENU,
}


class BotManager:
    """
    مدير البوتات المتقدم — المرحلة 13
    يُسجِّل البوتات، يُشغِّل معالجات الأوامر والـ callbacks،
    ويدعم machine-state وأوامر مدمجة.
    المستودع: anwer1230/Abu_Mlk
    """

    def __init__(self, db=None):
        self.db              = db
        self._bots:   dict   = {}
        self._commands: Dict[str, List[BotCommand]] = {}
        self._callbacks: Dict[str, List[BotCallback]] = {}
        self._states: Dict[str, BotState] = {}
        self._lock           = threading.Lock()
        logger.info('BotManager (M13): تم التهيئة')

    # ══════════════════════════════════════════════════════
    #  التهيئة
    # ══════════════════════════════════════════════════════

    def init_app(self):
        """تهيئة البوتات عند بدء التطبيق."""
        logger.info('BotManager: init_app() — تحميل البوتات')
        bots = self._db_list_bots()
        for bot in bots:
            if bot.get('is_active'):
                self._try_start_bot(bot)
        logger.info(f'BotManager: {len(bots)} بوت محمّل')

    # ══════════════════════════════════════════════════════
    #  إدارة البوتات
    # ══════════════════════════════════════════════════════

    def register_bot(self, name: str, handler: Callable = None,
                     phone: str = None, api_id: str = None,
                     api_hash: str = None, user_id: str = None) -> int:
        with self._lock:
            self._bots[name] = {
                'name': name, 'handler': handler, 'phone': phone,
                'api_id': api_id, 'api_hash': api_hash,
                'user_id': user_id, 'active': True,
            }
        # الأوامر المدمجة
        self._commands.setdefault(name, [])
        for cmd, reply in BUILTIN_COMMANDS.items():
            self._commands[name].append(
                BotCommand(cmd, reply, self._builtin_reply_handler(reply), False)
            )
        bot_id = self._db_save_bot(name, phone, api_id, api_hash, user_id)
        logger.info(f'BotManager: تم تسجيل "{name}" (id={bot_id})')
        return bot_id

    def register_command(self, bot_name: str, command: str,
                         handler: Callable, description: str = '',
                         admin_only: bool = False):
        self._commands.setdefault(bot_name, []).append(
            BotCommand(command, description, handler, admin_only)
        )
        self._db_save_command(bot_name, command, description)

    def register_callback(self, bot_name: str, data: str,
                          handler: Callable, admin_only: bool = False):
        self._callbacks.setdefault(bot_name, []).append(
            BotCallback(data, handler, admin_only)
        )

    def get_bot(self, name: str) -> Optional[dict]:
        with self._lock:
            return self._bots.get(name)

    def list_bots(self) -> list:
        with self._lock:
            return list(self._bots.values())

    def stop_all(self):
        with self._lock:
            self._bots.clear()
        logger.info('BotManager: جميع البوتات أُوقفت')

    # ══════════════════════════════════════════════════════
    #  معالجة الرسائل
    # ══════════════════════════════════════════════════════

    async def process_message(self, bot_name: str, event) -> Optional[str]:
        """معالجة رسالة واردة — أوامر، حالات، رسائل عادية."""
        msg = getattr(event, 'message', None)
        if not msg or not getattr(msg, 'text', None):
            return None

        user_id = getattr(event, 'sender_id', None)
        chat_id = getattr(event, 'chat_id', None)
        text    = msg.text.strip()

        # ─── فحص الحالة أولاً ────────────────────────────
        state_key = f'{user_id}_{chat_id}'
        if state_key in self._states:
            return await self._handle_state(bot_name, event, self._states[state_key])

        # ─── معالجة الأوامر ──────────────────────────────
        if text.startswith('/'):
            return await self._dispatch_command(bot_name, event, text)

        # ─── رسالة عادية ─────────────────────────────────
        return await self._handle_regular(bot_name, event, text)

    async def process_callback(self, bot_name: str, event) -> Optional[str]:
        """معالجة ضغطة زر inline."""
        data    = event.data.decode('utf-8') if isinstance(event.data, bytes) else event.data
        user_id = getattr(event, 'sender_id', None)

        # فحص الصلاحيات وتوجيه
        for cb in self._callbacks.get(bot_name, []):
            if cb.data == data:
                if cb.admin_only and not await self._is_admin(user_id, getattr(event, 'chat_id', None)):
                    await event.answer('⚠️ هذا الزر للمشرفين فقط', alert=True)
                    return None
                return await cb.handler(event, bot_name)

        # القوائم المدمجة
        if data in CALLBACK_MENUS:
            menu = CALLBACK_MENUS[data]
            await event.edit(menu['text'], buttons=self._make_buttons(menu['buttons']))
            return None

        await event.answer('❌ الزر غير مفعّل', alert=True)
        return None

    # ══════════════════════════════════════════════════════
    #  إدارة الحالات (State Machine)
    # ══════════════════════════════════════════════════════

    def set_state(self, user_id: int, chat_id: int, state: str, data: dict = None):
        key = f'{user_id}_{chat_id}'
        self._states[key] = BotState(user_id, chat_id, state, data or {})
        self._db_save_state(user_id, chat_id, state, data or {})

    def clear_state(self, user_id: int, chat_id: int):
        key = f'{user_id}_{chat_id}'
        self._states.pop(key, None)

    async def _handle_state(self, bot_name: str, event, state: BotState) -> Optional[str]:
        if state.state == 'waiting_for_name':
            name = event.message.text.strip()
            self.clear_state(state.user_id, state.chat_id)
            return f'✅ شكراً {name}! سيتواصل معك فريقنا قريباً.'
        if state.state == 'waiting_for_input':
            self.clear_state(state.user_id, state.chat_id)
            return '✅ تم استلام طلبك!'
        return None

    # ══════════════════════════════════════════════════════
    #  أدوات داخلية
    # ══════════════════════════════════════════════════════

    def _builtin_reply_handler(self, reply: str) -> Callable:
        async def _h(event, bot_name):
            await event.reply(reply)
        return _h

    async def _dispatch_command(self, bot_name: str, event, text: str):
        cmd = text.split()[0].lower().split('@')[0]
        for bc in self._commands.get(bot_name, []):
            if bc.command == cmd:
                user_id = getattr(event, 'sender_id', None)
                chat_id = getattr(event, 'chat_id', None)
                if bc.admin_only and not await self._is_admin(user_id, chat_id):
                    await event.reply('⚠️ هذا الأمر للمشرفين فقط')
                    return None
                return await bc.handler(event, bot_name)
        return None

    async def _handle_regular(self, bot_name: str, event, text: str):
        # يمكن تخصيصها
        return None

    async def _is_admin(self, user_id: int, chat_id: int) -> bool:
        if not self.db:
            return False
        try:
            with self.db.get_connection() as conn:
                row = conn.execute(
                    'SELECT 1 FROM bot_admins WHERE user_id=? AND (chat_id=? OR chat_id IS NULL)',
                    (str(user_id), str(chat_id))
                ).fetchone()
            return row is not None
        except Exception:
            return False

    def _make_buttons(self, rows: list):
        """تحويل قائمة الأزرار إلى Telethon InlineKeyboardMarkup."""
        try:
            from telethon.tl.types import (
                InlineKeyboardMarkup, InlineKeyboardButton, KeyboardButtonUrl
            )
            kb_rows = []
            for row in rows:
                kb_row = []
                for btn in row:
                    if 'url' in btn:
                        kb_row.append(KeyboardButtonUrl(btn['text'], btn['url']))
                    else:
                        kb_row.append(InlineKeyboardButton(btn['text'], btn.get('data', '').encode()))
                kb_rows.append(kb_row)
            return InlineKeyboardMarkup(kb_rows)
        except ImportError:
            return None

    def _try_start_bot(self, bot: dict):
        """محاولة تشغيل بوت مسجّل."""
        name = bot.get('name', '')
        if not name:
            return
        with self._lock:
            self._bots[name] = {**bot, 'active': True}
        self._commands.setdefault(name, [])
        for cmd, reply in BUILTIN_COMMANDS.items():
            self._commands[name].append(
                BotCommand(cmd, reply, self._builtin_reply_handler(reply), False)
            )
        logger.info(f'BotManager: بوت "{name}" جاهز')

    # ══════════════════════════════════════════════════════
    #  قاعدة البيانات
    # ══════════════════════════════════════════════════════

    def _db_save_bot(self, name, phone, api_id, api_hash, user_id) -> int:
        if not self.db:
            return -1
        try:
            with self.db.get_connection() as conn:
                cur = conn.cursor()
                cur.execute('''
                    INSERT OR IGNORE INTO bots (name, phone, api_id, api_hash, user_id)
                    VALUES (?, ?, ?, ?, ?)
                ''', (name, phone, api_id, api_hash, user_id))
                return cur.lastrowid or -1
        except Exception as e:
            logger.warning(f'_db_save_bot: {e}')
            return -1

    def _db_save_command(self, bot_name, command, description=''):
        if not self.db:
            return
        try:
            with self.db.get_connection() as conn:
                row = conn.execute(
                    'SELECT id FROM bots WHERE name=?', (bot_name,)
                ).fetchone()
                if row:
                    conn.execute('''
                        INSERT OR REPLACE INTO bot_commands (bot_id, command, description)
                        VALUES (?, ?, ?)
                    ''', (row['id'], command, description))
        except Exception as e:
            logger.warning(f'_db_save_command: {e}')

    def _db_list_bots(self) -> list:
        if not self.db:
            return []
        try:
            with self.db.get_connection() as conn:
                rows = conn.execute(
                    'SELECT * FROM bots WHERE is_active=1'
                ).fetchall()
            return [dict(r) for r in rows]
        except Exception as e:
            logger.warning(f'_db_list_bots: {e}')
            return []

    def _db_save_state(self, user_id, chat_id, state, data):
        if not self.db:
            return
        try:
            with self.db.get_connection() as conn:
                conn.execute('''
                    INSERT OR REPLACE INTO bot_states (user_id, chat_id, state, data)
                    VALUES (?, ?, ?, ?)
                ''', (str(user_id), str(chat_id), state, json.dumps(data)))
        except Exception as e:
            logger.warning(f'_db_save_state: {e}')
