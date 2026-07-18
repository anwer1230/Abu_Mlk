"""
main.py — نقطة الدخول الرئيسية لمركز سرعة إنجاز
يُشغَّل بواسطة: python main.py
"""

import os
from config import Config

Config.ensure_dirs()

from app import socketio, app

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"🚀 مركز سرعة إنجاز — يعمل على المنفذ {port}")
    socketio.run(
        app,
        host='0.0.0.0',
        port=port,
        debug=Config.DEBUG,
        allow_unsafe_werkzeug=True,
    )
