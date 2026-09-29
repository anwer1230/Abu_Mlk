"""Entry point - runs the Abu_Malk-Services app."""
import os
import sys
import subprocess
import signal
import logging

# التأكد التلقائي من توفر الحزم الأساسية لمنع أي عطل عند إعادة تشغيل البيئة
try:
    import requests
    import flask
    import flask_socketio
except ImportError:
    print("⏳ جارٍ تهيئة وتثبيت حزم بايثون الأساسية تلقائياً...")
    try:
        subprocess.run(["pip", "install", "--break-system-packages", "-r", "requirements.txt"], check=True)
    except Exception:
        subprocess.run(["sh", "-c", "curl -sS https://bootstrap.pypa.io/get-pip.py | python3 - --break-system-packages && pip install --break-system-packages -r requirements.txt"], check=True)

from app import app, socketio

def free_port(port):
    """تحرير المنفذ إذا كان مشغولاً (للبيئات المحلية فقط)"""
    try:
        if os.environ.get('RENDER'):
            return
            
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        result = s.connect_ex(('127.0.0.1', port))
        s.close()
        if result == 0:
            import subprocess
            subprocess.run(['fuser', '-k', f'{port}/tcp'], capture_output=True)
            import time
            time.sleep(1)
    except Exception:
        pass

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 3000))
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    if os.environ.get('RENDER'):
        print(f"🌐 تشغيل Abu_Malk-Services على المنفذ {port} في بيئة Render")
        socketio.run(app, host='0.0.0.0', port=port, allow_unsafe_werkzeug=True)
    else:
        free_port(port)
        print(f"🌐 تشغيل Abu_Malk-Services على المنفذ {port}")
        socketio.run(app, host='0.0.0.0', port=port, debug=False, allow_unsafe_werkzeug=True)
