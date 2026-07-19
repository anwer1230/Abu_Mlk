"""
upload_handler.py — مركز سرعة إنجاز
══════════════════════════════════════════════════════════════
وحدة رفع الملفات المتدفق (Chunked Streaming Upload)
المرحلة 7: رفع الملفات الكبيرة بأجزاء مع تتبع التقدم
══════════════════════════════════════════════════════════════
"""

import os
import uuid
import logging
from datetime import datetime

from flask import request, jsonify, send_from_directory, session

logger = logging.getLogger(__name__)

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), 'uploads')
CHUNK_DIR  = os.path.join(UPLOAD_DIR, '.chunks')


class UploadHandler:
    """مُعالج رفع الملفات — رفع متدفق بالأجزاء مع تتبع التقدم."""

    def __init__(self, app, db=None):
        self.app = app
        self.db  = db
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        os.makedirs(CHUNK_DIR,  exist_ok=True)
        self._register_routes()
        logger.info("UploadHandler: تم التهيئة وتسجيل المسارات")

    # ── مساعدات ────────────────────────────────────────────────────────

    def _is_auth(self):
        return bool(session.get('user_id'))

    def _user_id(self):
        return session.get('user_id', 'anonymous')

    def _db_save_upload(self, upload_id: str, filename: str,
                        original_name: str, total_chunks: int,
                        size: int = 0):
        """حفظ سجل رفع جديد في قاعدة البيانات."""
        if not self.db:
            return
        try:
            with self.db.get_connection() as conn:
                conn.execute('''
                    INSERT OR REPLACE INTO uploads
                    (id, filename, original_name, size, total_chunks,
                     uploaded_chunks, user_id, status)
                    VALUES (?, ?, ?, ?, ?, 0, ?, 'uploading')
                ''', (upload_id, filename, original_name,
                      size, total_chunks, self._user_id()))
        except Exception as e:
            logger.warning(f"_db_save_upload error: {e}")

    def _db_update_chunk(self, upload_id: str, uploaded_chunks: int,
                         status: str = None, url: str = None):
        if not self.db:
            return
        try:
            with self.db.get_connection() as conn:
                if status and url:
                    conn.execute('''
                        UPDATE uploads
                        SET uploaded_chunks = ?,
                            status          = ?,
                            url             = ?,
                            completed_at    = CURRENT_TIMESTAMP
                        WHERE id = ?
                    ''', (uploaded_chunks, status, url, upload_id))
                elif status:
                    conn.execute('''
                        UPDATE uploads
                        SET uploaded_chunks = ?,
                            status          = ?
                        WHERE id = ?
                    ''', (uploaded_chunks, status, upload_id))
                else:
                    conn.execute('''
                        UPDATE uploads
                        SET uploaded_chunks = ?
                        WHERE id = ?
                    ''', (uploaded_chunks, upload_id))
        except Exception as e:
            logger.warning(f"_db_update_chunk error: {e}")

    def _db_get_upload(self, upload_id: str) -> dict | None:
        if not self.db:
            return None
        try:
            with self.db.get_connection() as conn:
                row = conn.execute(
                    'SELECT * FROM uploads WHERE id = ?', (upload_id,)
                ).fetchone()
            return dict(row) if row else None
        except Exception as e:
            logger.warning(f"_db_get_upload error: {e}")
            return None

    # ── تسجيل المسارات ─────────────────────────────────────────────────

    def _register_routes(self):
        app = self.app

        # ─── بدء جلسة رفع ────────────────────────────────────────────
        @app.route('/api/upload/start', methods=['POST'])
        def api_upload_start():
            if not self._is_auth():
                return jsonify({'success': False, 'message': 'غير مسجل الدخول'}), 401

            data          = request.get_json(force=True) or {}
            original_name = (data.get('filename') or 'file').strip()
            file_size     = int(data.get('size', 0))
            chunk_size    = int(data.get('chunkSize', 2 * 1024 * 1024))  # 2MB افتراضياً

            # اسم آمن للملف
            ext      = os.path.splitext(original_name)[-1]
            safe_ext = ext[:10] if ext else ''
            upload_id  = str(uuid.uuid4())
            filename   = f"{upload_id}{safe_ext}"

            total_chunks = max(1, -(-file_size // chunk_size)) if file_size else 1

            # إنشاء مجلد الأجزاء لهذا الرفع
            os.makedirs(os.path.join(CHUNK_DIR, upload_id), exist_ok=True)

            self._db_save_upload(upload_id, filename, original_name,
                                 total_chunks, file_size)

            logger.info(f"⬆️ رفع جديد: {original_name} ({file_size} بايت) "
                        f"→ {total_chunks} جزء")

            return jsonify({
                'success':      True,
                'upload_id':    upload_id,
                'chunk_size':   chunk_size,
                'total_chunks': total_chunks,
            })

        # ─── رفع جزء ─────────────────────────────────────────────────
        @app.route('/api/upload/chunk', methods=['POST'])
        def api_upload_chunk():
            if not self._is_auth():
                return jsonify({'success': False, 'message': 'غير مسجل الدخول'}), 401

            upload_id   = request.form.get('upload_id', '').strip()
            chunk_index = request.form.get('chunk_index', type=int)

            if not upload_id or chunk_index is None:
                return jsonify({'success': False,
                                'message': 'upload_id و chunk_index مطلوبان'}), 400

            chunk_file = request.files.get('chunk')
            if not chunk_file:
                return jsonify({'success': False, 'message': 'لم يُرسل أي جزء'}), 400

            # حفظ الجزء
            chunk_path = os.path.join(CHUNK_DIR, upload_id,
                                      f'chunk_{chunk_index:06d}')
            try:
                chunk_file.save(chunk_path)
            except Exception as e:
                logger.error(f"حفظ الجزء {chunk_index}: {e}")
                return jsonify({'success': False, 'message': str(e)}), 500

            # عدّ الأجزاء المكتملة
            chunks_done = len([
                f for f in os.listdir(os.path.join(CHUNK_DIR, upload_id))
                if f.startswith('chunk_')
            ])
            self._db_update_chunk(upload_id, chunks_done)

            return jsonify({
                'success':       True,
                'chunk_index':   chunk_index,
                'chunks_done':   chunks_done,
            })

        # ─── إتمام الرفع ──────────────────────────────────────────────
        @app.route('/api/upload/complete', methods=['POST'])
        def api_upload_complete():
            if not self._is_auth():
                return jsonify({'success': False, 'message': 'غير مسجل الدخول'}), 401

            data      = request.get_json(force=True) or {}
            upload_id = (data.get('upload_id') or '').strip()
            if not upload_id:
                return jsonify({'success': False,
                                'message': 'upload_id مطلوب'}), 400

            row = self._db_get_upload(upload_id)
            if not row:
                return jsonify({'success': False,
                                'message': 'جلسة الرفع غير موجودة'}), 404

            filename   = row.get('filename', f'{upload_id}.bin')
            chunk_dir  = os.path.join(CHUNK_DIR, upload_id)
            dest_path  = os.path.join(UPLOAD_DIR, filename)

            try:
                # دمج الأجزاء بالترتيب
                chunk_files = sorted([
                    f for f in os.listdir(chunk_dir) if f.startswith('chunk_')
                ])
                if not chunk_files:
                    return jsonify({'success': False,
                                    'message': 'لا توجد أجزاء للدمج'}), 400

                with open(dest_path, 'wb') as out:
                    for cf in chunk_files:
                        cp = os.path.join(chunk_dir, cf)
                        with open(cp, 'rb') as inp:
                            out.write(inp.read())

                # حذف الأجزاء المؤقتة
                import shutil
                shutil.rmtree(chunk_dir, ignore_errors=True)

                final_size = os.path.getsize(dest_path)
                url = f'/download/{filename}'
                self._db_update_chunk(upload_id,
                                      len(chunk_files),
                                      'completed', url)

                logger.info(f"✅ اكتمل الرفع: {filename} "
                            f"({final_size} بايت)")

                return jsonify({
                    'success':  True,
                    'filename': filename,
                    'original': row.get('original_name', filename),
                    'size':     final_size,
                    'url':      url,
                })

            except Exception as e:
                logger.error(f"إتمام الرفع {upload_id}: {e}")
                self._db_update_chunk(upload_id, 0, 'error')
                return jsonify({'success': False, 'message': str(e)}), 500

        # ─── حالة الرفع ──────────────────────────────────────────────
        @app.route('/api/upload/status/<upload_id>', methods=['GET'])
        def api_upload_status(upload_id):
            if not self._is_auth():
                return jsonify({'success': False, 'message': 'غير مسجل الدخول'}), 401

            row = self._db_get_upload(upload_id)
            if not row:
                return jsonify({'success': False,
                                'message': 'الرفع غير موجود'}), 404

            total    = row.get('total_chunks', 1) or 1
            done     = row.get('uploaded_chunks', 0) or 0
            progress = round(done / total * 100, 1)

            return jsonify({
                'success':       True,
                'upload_id':     upload_id,
                'status':        row.get('status'),
                'total_chunks':  total,
                'done_chunks':   done,
                'progress':      progress,
                'url':           row.get('url'),
                'original_name': row.get('original_name'),
            })

        # ─── تحميل الملف ─────────────────────────────────────────────
        @app.route('/download/<path:filename>', methods=['GET'])
        def download_file(filename):
            # السماح لأي مستخدم (رابط مباشر) — يمكن تقييده بـ auth
            safe_name = os.path.basename(filename)
            if not os.path.exists(os.path.join(UPLOAD_DIR, safe_name)):
                return jsonify({'success': False,
                                'message': 'الملف غير موجود'}), 404
            return send_from_directory(UPLOAD_DIR, safe_name, as_attachment=True)

        # ─── قائمة الملفات ───────────────────────────────────────────
        @app.route('/api/files', methods=['GET'])
        def api_list_files():
            if not self._is_auth():
                return jsonify({'success': False, 'message': 'غير مسجل الدخول'}), 401

            if self.db:
                try:
                    with self.db.get_connection() as conn:
                        rows = conn.execute('''
                            SELECT id, original_name, filename, size,
                                   status, url, created_at
                            FROM uploads
                            WHERE user_id = ? AND status = 'completed'
                            ORDER BY created_at DESC
                            LIMIT 100
                        ''', (self._user_id(),)).fetchall()
                    return jsonify({'success': True,
                                    'files': [dict(r) for r in rows]})
                except Exception as e:
                    logger.warning(f"api_list_files DB: {e}")

            # بديل: فهرسة المجلد مباشرة
            try:
                files = []
                for f in os.listdir(UPLOAD_DIR):
                    full = os.path.join(UPLOAD_DIR, f)
                    if os.path.isfile(full):
                        files.append({
                            'filename': f,
                            'size':     os.path.getsize(full),
                            'url':      f'/download/{f}',
                        })
                return jsonify({'success': True, 'files': files})
            except Exception as e:
                return jsonify({'success': False, 'message': str(e)}), 500

        # ─── رفع بسيط (متوافق خلفياً) ────────────────────────────────
        @app.route('/api/upload', methods=['POST'])
        def api_upload_simple():
            if not self._is_auth():
                return jsonify({'success': False, 'message': 'غير مسجل الدخول'}), 401

            if 'file' not in request.files:
                return jsonify({'success': False,
                                'message': 'لم يتم تحديد ملف'}), 400
            f = request.files['file']
            if not f.filename:
                return jsonify({'success': False,
                                'message': 'اسم الملف فارغ'}), 400

            try:
                upload_id = str(uuid.uuid4())
                ext       = os.path.splitext(f.filename)[-1][:10]
                filename  = f"{upload_id}{ext}"
                dest      = os.path.join(UPLOAD_DIR, filename)
                f.save(dest)
                size = os.path.getsize(dest)
                url  = f'/download/{filename}'
                self._db_save_upload(upload_id, filename, f.filename, 1, size)
                self._db_update_chunk(upload_id, 1, 'completed', url)
                return jsonify({
                    'success':  True,
                    'message':  'تم الرفع بنجاح',
                    'filename': filename,
                    'url':      url,
                })
            except Exception as e:
                logger.error(f"رفع بسيط: {e}")
                return jsonify({'success': False, 'message': str(e)}), 500
