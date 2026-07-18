"""
upload_handler.py — مركز سرعة إنجاز
══════════════════════════════════════════════════════════════
وحدة رفع الملفات — تسجيل مسارات الرفع في Flask
المستودع الأصلي: https://github.com/anwer1230/Abu_Mlk
══════════════════════════════════════════════════════════════
"""

import os
import logging

from flask import request, jsonify, session

logger = logging.getLogger(__name__)


class UploadHandler:
    """مُعالج رفع الملفات — يُسجّل مسارات API الخاصة بالملفات."""

    def __init__(self, app, db=None):
        self.app  = app
        self.db   = db
        self._register_routes()
        logger.info("UploadHandler: initialized and routes registered")

    def _register_routes(self):
        app = self.app

        @app.route('/api/upload', methods=['POST'])
        def api_upload_file():
            if 'file' not in request.files:
                return jsonify({'success': False, 'message': 'لم يتم تحديد ملف'}), 400
            f = request.files['file']
            if f.filename == '':
                return jsonify({'success': False, 'message': 'اسم الملف فارغ'}), 400
            try:
                upload_dir = os.path.join(os.path.dirname(__file__), 'uploads')
                os.makedirs(upload_dir, exist_ok=True)
                dest = os.path.join(upload_dir, f.filename)
                f.save(dest)
                return jsonify({'success': True, 'message': 'تم الرفع بنجاح', 'filename': f.filename})
            except Exception as e:
                logger.error(f"Upload error: {e}")
                return jsonify({'success': False, 'message': str(e)}), 500

        @app.route('/api/files', methods=['GET'])
        def api_list_files():
            upload_dir = os.path.join(os.path.dirname(__file__), 'uploads')
            os.makedirs(upload_dir, exist_ok=True)
            try:
                files = [
                    f for f in os.listdir(upload_dir)
                    if os.path.isfile(os.path.join(upload_dir, f))
                ]
                return jsonify({'success': True, 'files': files})
            except Exception as e:
                return jsonify({'success': False, 'message': str(e)}), 500
