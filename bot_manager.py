"""
bot_manager.py — مركز سرعة إنجاز
══════════════════════════════════════════════════════════════
وحدة إدارة البوتات التفاعلية (المرحلة 8)
يدعم: أوامر البوت، الأزرار المدمجة، المعالجات التلقائية
══════════════════════════════════════════════════════════════
"""

import os
import logging
import threading
from typing import Callable

logger = logging.getLogger(__name__)

# ─── المعالجات المدمجة ────────────────────────────────────────────────────

BUILTIN_COMMANDS = {
    '/start': 'مرحباً! أنا بوت مركز سرعة إنجاز. اكتب /help لعرض الأوامر.',
    '/help': (
        'الأوامر المتاحة:\n'
        '/start — الترحيب\n'
        '/help — قائمة الأوامر\n'
        '/status — حالة الخادم\n'
        '/ping — اختبار الاتصال'
    ),
    '/ping': 'Pong! 🏓',
    '/status': 'الخادم يعمل بشكل طبيعي ✅',
}


class BotManager:
    """
    مدير البوتات التفاعلية.
    يُسجِّل البوتات، يُشغِّل معالجات الأوامر والـ callbacks،
    ويتكامل مع قاعدة البيانات لحفظ الإعدادات.
    """

    def __init__(self, db=None):
        self.db            = db
        self._bots: dict   = {}           # {bot_name: BotSession}
        self._commands: dict = {}         # {bot_name: {cmd: handler_fn}}
        self._callbacks: dict = {}        # {bot_name: {data: handler_fn}}
        self._lock         = threading.Lock()
        logger.info("BotManager: تم التهيئة")

    # ══════════════════════════════════════════════════════════════════
    #  التهيئة
    # ══════════════════════════════════════════════════════════════════

    def init_app(self):
        """تهيئة البوتات عند بدء التطبيق — يُحمِّل من قاعدة البيانات."""
        logger.info("BotManager: init_app() — تحميل البوتات من قاعدة البيانات")
        bots = self._db_list_bots()
        for bot in bots:
            if bot.get('is_active'):
                self._try_start_bot(bot)
        logger.info(f"BotManager: {len(bots)} بوت محمّل")

    # ══════════════════════════════════════════════════════════════════
    #  إدارة البوتات
    # ══════════════════════════════════════════════════════════════════

    def register_bot(self, name: str, handler: Callable = None,
                     phone: str = None, api_id: str = None,
                     api_hash: str = None, user_id: str = None) -> int:
        """تسجيل بوت جديد وحفظه في قاعدة البيانات."""
        with self._lock:
            self._bots[name] = {
                'name':     name,
                'handler':  handler,
                'phone':    phone,
                'api_id':   api_id,
                'api_hash': api_hash,
                'user_id':  user_id,
                'active':   True,
            }

        # تسجيل الأوامر المدمجة
        self._commands.setdefault(name, {}).update(BUILTIN_COMMANDS)

        bot_id = self._db_save_bot(name, phone, api_id, api_hash, user_id)
        logger.info(f"BotManager: تم تسجيل البوت '{name}' (id={bot_id})")
        return bot_id

    def register_command(self, bot_name: str, command: str,
                         handler: Callable, description: str = ''):
        """تسجيل أمر لبوت معين."""
        self._commands.setdefault(bot_name, {})[command] = handler
        self._db_save_command(bot_name, command, description)
        logger.info(f"BotManager: أمر '{command}' → '{bot_name}'")

    def register_callback(self, bot_name: str, callback_data: str,
                          handler: Callable):
        """تسجيل معالج callback."""
        self._callbacks.setdefault(bot_name, {})[callback_data] = handler

    def get_bot(self, name: str) -> dict | None:
        with self._lock:
            return self._bots.get(name)

    def list_bots(self) -> list:
        with self._lock:
            return list(self._bots.values())

    def stop_all(self):
        """إيقاف جميع البوتات (تنظيف عند إغلاق التطبيق)."""
        with self._lock:
            for name in list(self._bots.keys()):
                self._stop_bot(name)
        logger.info("BotManager: جميع البوتات متوقفة")

    # ══════════════════════════════════════════════════════════════════
    #  معالجة الرسائل / الأوامر
    # ══════════════════════════════════════════════════════════════════

    def handle_message(self, bot_name: str, sender_id: str,
                       text: str, raw=None) -> str | None:
        """
        معالجة رسالة واردة لبوت.
        يُعيد نص الرد إن وُجد، أو None.
        """
        text = (text or '').strip()
        if not text:
            return None

        # أوامر /command
        if text.startswith('/'):
            cmd = text.split()[0].lower()
            # أولاً: المعالجات المسجّلة للبوت
            handler = self._commands.get(bot_name, {}).get(cmd)
            if handler and callable(handler):
                try:
                    return handler(sender_id=sender_id, text=text, raw=raw)
                except Exception as e:
                    logger.error(f"handler '{cmd}' error: {e}")
                    return 'حدث خطأ في معالجة الأمر'
            # ثانياً: الأوامر المدمجة
            if cmd in BUILTIN_COMMANDS:
                return BUILTIN_COMMANDS[cmd]

        logger.debug(f"BotManager[{bot_name}]: رسالة غير مُعالَجة: {text[:60]}")
        return None

    def handle_callback(self, bot_name: str, sender_id: str,
                        callback_data: str, raw=None) -> str | None:
        """معالجة ضغطة زر callback_query."""
        handler = self._callbacks.get(bot_name, {}).get(callback_data)
        if handler and callable(handler):
            try:
                return handler(sender_id=sender_id,
                               callback_data=callback_data, raw=raw)
            except Exception as e:
                logger.error(f"callback '{callback_data}' error: {e}")
                return 'خطأ في المعالجة'
        return None

    # ══════════════════════════════════════════════════════════════════
    #  التكامل مع Telethon (اختياري — يُشغَّل في thread منفصل)
    # ══════════════════════════════════════════════════════════════════

    def _try_start_bot(self, bot: dict):
        """محاولة تشغيل بوت Telethon في خلفية (يتجاهل الأخطاء)."""
        name = bot.get('name', 'unknown')
        api_id   = bot.get('api_id')   or os.environ.get('TDLIB_API_ID')
        api_hash = bot.get('api_hash') or os.environ.get('TDLIB_API_HASH')
        user_id  = bot.get('user_id')

        if not api_id or not api_hash or not user_id:
            logger.debug(f"BotManager: '{name}' — بيانات ناقصة، يُتخطى")
            return

        with self._lock:
            self._bots[name] = {**bot, 'active': True}
        self._commands.setdefault(name, {}).update(BUILTIN_COMMANDS)

        t = threading.Thread(
            target=self._run_telethon_listener,
            args=(name, str(api_id), str(api_hash), str(user_id)),
            daemon=True,
            name=f'bot-{name}',
        )
        t.start()

    def _run_telethon_listener(self, bot_name: str,
                                api_id: str, api_hash: str, user_id: str):
        """مستمع Telethon لأحداث الرسائل — يعمل في thread منفصل."""
        import asyncio
        try:
            from telethon import TelegramClient, events
            from telethon.sessions import StringSession
            from auth import load_string_session

            ss = load_string_session(user_id)
            if not ss:
                logger.debug(f"BotManager[{bot_name}]: لا توجد جلسة لـ {user_id}")
                return

            loop = asyncio.new_event_loop()

            async def _run():
                client = TelegramClient(
                    StringSession(ss), int(api_id), api_hash, loop=loop
                )
                await client.connect()
                if not await client.is_user_authorized():
                    logger.warning(f"BotManager[{bot_name}]: الجلسة غير مُصرَّح بها")
                    await client.disconnect()
                    return

                @client.on(events.NewMessage(incoming=True))
                async def _msg_handler(event):
                    sender_id = str(event.sender_id)
                    text      = event.text or ''
                    reply     = self.handle_message(bot_name, sender_id, text, event)
                    if reply:
                        await event.reply(reply)

                logger.info(f"🤖 BotManager[{bot_name}]: مستمع نشط")
                await client.run_until_disconnected()

            loop.run_until_complete(_run())

        except Exception as e:
            logger.debug(f"BotManager[{bot_name}] listener stopped: {e}")

    def _stop_bot(self, name: str):
        bot = self._bots.pop(name, None)
        if bot:
            logger.info(f"BotManager: إيقاف البوت '{name}'")

    # ══════════════════════════════════════════════════════════════════
    #  قاعدة البيانات
    # ══════════════════════════════════════════════════════════════════

    def _db_save_bot(self, name: str, phone: str = None,
                     api_id: str = None, api_hash: str = None,
                     user_id: str = None) -> int:
        if not self.db:
            return -1
        try:
            with self.db.get_connection() as conn:
                cur = conn.cursor()
                cur.execute('''
                    INSERT INTO bots (name, phone, api_id, api_hash, user_id)
                    VALUES (?, ?, ?, ?, ?)
                ''', (name, phone, api_id, api_hash, user_id))
                return cur.lastrowid
        except Exception as e:
            logger.warning(f"_db_save_bot: {e}")
            return -1

    def _db_save_command(self, bot_name: str, command: str,
                         description: str = ''):
        if not self.db:
            return
        try:
            with self.db.get_connection() as conn:
                row = conn.execute(
                    'SELECT id FROM bots WHERE name = ?', (bot_name,)
                ).fetchone()
                if not row:
                    return
                conn.execute('''
                    INSERT OR REPLACE INTO bot_commands
                    (bot_id, command, description)
                    VALUES (?, ?, ?)
                ''', (row['id'], command, description))
        except Exception as e:
            logger.warning(f"_db_save_command: {e}")

    def _db_list_bots(self) -> list:
        if not self.db:
            return []
        try:
            with self.db.get_connection() as conn:
                rows = conn.execute(
                    'SELECT * FROM bots WHERE is_active = 1'
                ).fetchall()
            return [dict(r) for r in rows]
        except Exception as e:
            logger.warning(f"_db_list_bots: {e}")
            return []
