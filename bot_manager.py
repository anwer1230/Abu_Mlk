"""
bot_manager.py — مركز سرعة إنجاز
══════════════════════════════════════════════════════════════
وحدة إدارة البوتات التفاعلية — تهيئة أولية
المستودع الأصلي: https://github.com/anwer1230/Abu_Mlk
══════════════════════════════════════════════════════════════
"""

import logging

logger = logging.getLogger(__name__)


class BotManager:
    """مدير البوتات — يُعرِّف بوتات المنصة ويُشغّلها."""

    def __init__(self, db=None):
        self.db = db
        self._bots = {}
        logger.info("BotManager: initialized")

    def init_app(self):
        """تهيئة البوتات عند بدء التطبيق."""
        logger.info("BotManager: init_app() called")

    def register_bot(self, name, handler):
        self._bots[name] = handler
        logger.info(f"BotManager: registered bot '{name}'")

    def get_bot(self, name):
        return self._bots.get(name)

    def stop_all(self):
        logger.info("BotManager: stop_all() called")
