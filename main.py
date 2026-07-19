"""
main.py — مركز سرعة إنجاز
نقطة الدخول الرئيسية للتطبيق (المراحل 1-15)
المستودع الأصلي: https://github.com/anwer1230/Abu_Mlk
"""

import os
import sys

# تأكد من وجود المجلدات الضرورية
os.makedirs('sessions', exist_ok=True)
os.makedirs('uploads', exist_ok=True)
os.makedirs('uploads/temp', exist_ok=True)
os.makedirs('data', exist_ok=True)
os.makedirs('static/css', exist_ok=True)
os.makedirs('static/js', exist_ok=True)
os.makedirs('static/icons', exist_ok=True)

from app import app, socketio
from config import Config

if __name__ == '__main__':
    import logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    )
    logger = logging.getLogger(__name__)
    logger.info("🚀 تشغيل مركز سرعة إنجاز — المراحل 1-15 المتكاملة")
    logger.info(f"📦 قاعدة البيانات: {Config.DATABASE}")
    logger.info(f"🔗 المستودع الدائم: {Config.GITHUB_REPO}")
    socketio.run(
        app,
        host=Config.SOCKET_HOST,
        port=Config.SOCKET_PORT,
        debug=Config.DEBUG,
        allow_unsafe_werkzeug=True,
    )
