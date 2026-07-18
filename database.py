# database.py — مركز سرعة إنجاز
# ═══════════════════════════════════════════════════════════════════════════
# قاعدة بيانات SQLite محلية + مزامنة تلقائية مع GitHub (anwer1230/Abu_Mlk)
# المستودع الأصلي: https://github.com/anwer1230/Abu_Mlk
# ═══════════════════════════════════════════════════════════════════════════

import sqlite3
import json
import logging
import os
from datetime import datetime
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class Database:
    """
    طبقة البيانات الموحدة — SQLite محلي + GitHub كنسخة احتياطية دائمة.
    قاعدة البيانات الأساسية: anwer1230/Abu_Mlk
    """

    def __init__(self, db_path: str = None):
        if db_path is None:
            from config import Config
            db_path = Config.DATABASE
        self.db_path = db_path
        self.init_db()

    # ── اتصال ──────────────────────────────────────────────────────────────
    @contextmanager
    def get_connection(self):
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"DB error: {e}")
            raise
        finally:
            conn.close()

    # ── تهيئة الجداول ──────────────────────────────────────────────────────
    def init_db(self):
        """إنشاء / ترقية جميع الجداول."""
        with self.get_connection() as conn:
            cur = conn.cursor()

            # ── المستخدمون ──────────────────────────────────────────────────
            cur.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id      TEXT UNIQUE NOT NULL,
                    phone        TEXT,
                    name         TEXT,
                    username     TEXT,
                    session_file TEXT,
                    string_session TEXT,
                    is_active    BOOLEAN DEFAULT 1,
                    created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
                    last_login   DATETIME
                )
            ''')

            # ── الجلسات ──────────────────────────────────────────────────────
            cur.execute('''
                CREATE TABLE IF NOT EXISTS sessions (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id      TEXT NOT NULL,
                    session_data TEXT NOT NULL,
                    created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
                    expires_at   DATETIME,
                    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
                )
            ''')

            # ── المجلدات المشتركة ────────────────────────────────────────────
            cur.execute('''
                CREATE TABLE IF NOT EXISTS shared_folders (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    name       TEXT NOT NULL,
                    icon       TEXT DEFAULT '📁',
                    owner_id   TEXT NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    is_active  BOOLEAN DEFAULT 1
                )
            ''')

            cur.execute('''
                CREATE TABLE IF NOT EXISTS folder_members (
                    folder_id        INTEGER NOT NULL,
                    user_id          TEXT NOT NULL,
                    permission_level INTEGER DEFAULT 1,
                    joined_at        DATETIME DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (folder_id, user_id),
                    FOREIGN KEY (folder_id) REFERENCES shared_folders(id) ON DELETE CASCADE
                )
            ''')

            cur.execute('''
                CREATE TABLE IF NOT EXISTS folder_chats (
                    folder_id  INTEGER NOT NULL,
                    chat_id    TEXT NOT NULL,
                    chat_title TEXT,
                    added_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (folder_id, chat_id),
                    FOREIGN KEY (folder_id) REFERENCES shared_folders(id) ON DELETE CASCADE
                )
            ''')

            # ── إعدادات المستخدمين ───────────────────────────────────────────
            cur.execute('''
                CREATE TABLE IF NOT EXISTS user_settings (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id    TEXT NOT NULL,
                    key        TEXT NOT NULL,
                    value      TEXT,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE (user_id, key),
                    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
                )
            ''')

            # ── سجل الأنشطة ──────────────────────────────────────────────────
            cur.execute('''
                CREATE TABLE IF NOT EXISTS activity_log (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id    TEXT,
                    action     TEXT NOT NULL,
                    details    TEXT,
                    ip_address TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # ── بطاقات التفعيل ───────────────────────────────────────────────
            cur.execute('''
                CREATE TABLE IF NOT EXISTS activation_cards (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    code       TEXT UNIQUE NOT NULL,
                    is_used    BOOLEAN DEFAULT 0,
                    used_by    TEXT,
                    used_at    DATETIME,
                    expires_at DATETIME,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # ── اشتراكات Push ────────────────────────────────────────────────
            cur.execute('''
                CREATE TABLE IF NOT EXISTS push_subscriptions (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id      TEXT NOT NULL,
                    subscription TEXT NOT NULL,
                    created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
                )
            ''')

            conn.commit()
            logger.info("✅ تم تهيئة قاعدة البيانات بنجاح")

    # ── المستخدمون ─────────────────────────────────────────────────────────

    def get_user(self, user_id: str) -> dict | None:
        with self.get_connection() as conn:
            row = conn.execute('SELECT * FROM users WHERE user_id = ?', (str(user_id),)).fetchone()
        return dict(row) if row else None

    def upsert_user(self, user_id: str, phone: str = None, name: str = None,
                    username: str = None, string_session: str = None) -> bool:
        try:
            with self.get_connection() as conn:
                conn.execute('''
                    INSERT INTO users (user_id, phone, name, username, string_session,
                                       session_file, last_login)
                    VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(user_id) DO UPDATE SET
                        phone          = COALESCE(excluded.phone, phone),
                        name           = COALESCE(excluded.name, name),
                        username       = COALESCE(excluded.username, username),
                        string_session = COALESCE(excluded.string_session, string_session),
                        last_login     = CURRENT_TIMESTAMP
                ''', (
                    str(user_id), phone, name, username, string_session,
                    f'sessions/{user_id}/{user_id}.session'
                ))
            return True
        except Exception as e:
            logger.error(f"upsert_user error: {e}")
            return False

    def get_all_users(self) -> list:
        with self.get_connection() as conn:
            rows = conn.execute(
                'SELECT user_id, name, phone, username, is_active, last_login '
                'FROM users ORDER BY created_at'
            ).fetchall()
        return [dict(r) for r in rows]

    def set_user_active(self, user_id: str, active: bool) -> bool:
        try:
            with self.get_connection() as conn:
                conn.execute('UPDATE users SET is_active = ? WHERE user_id = ?',
                             (1 if active else 0, str(user_id)))
            return True
        except Exception as e:
            logger.error(f"set_user_active error: {e}")
            return False

    # ── إعدادات المستخدمين ─────────────────────────────────────────────────

    def get_setting(self, user_id: str, key: str, default=None):
        with self.get_connection() as conn:
            row = conn.execute(
                'SELECT value FROM user_settings WHERE user_id = ? AND key = ?',
                (str(user_id), key)
            ).fetchone()
        if row:
            try:
                return json.loads(row['value'])
            except Exception:
                return row['value']
        return default

    def set_setting(self, user_id: str, key: str, value) -> bool:
        try:
            with self.get_connection() as conn:
                conn.execute('''
                    INSERT INTO user_settings (user_id, key, value, updated_at)
                    VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(user_id, key) DO UPDATE SET
                        value = excluded.value,
                        updated_at = CURRENT_TIMESTAMP
                ''', (str(user_id), key, json.dumps(value, ensure_ascii=False)))
            return True
        except Exception as e:
            logger.error(f"set_setting error: {e}")
            return False

    def get_all_settings(self, user_id: str) -> dict:
        with self.get_connection() as conn:
            rows = conn.execute(
                'SELECT key, value FROM user_settings WHERE user_id = ?', (str(user_id),)
            ).fetchall()
        result = {}
        for row in rows:
            try:
                result[row['key']] = json.loads(row['value'])
            except Exception:
                result[row['key']] = row['value']
        return result

    # ── سجل الأنشطة ──────────────────────────────────────────────────────
    def log_activity(self, user_id: str, action: str, details: str = None,
                     ip_address: str = None):
        try:
            with self.get_connection() as conn:
                conn.execute('''
                    INSERT INTO activity_log (user_id, action, details, ip_address)
                    VALUES (?, ?, ?, ?)
                ''', (str(user_id) if user_id else None, action, details, ip_address))
        except Exception as e:
            logger.error(f"log_activity error: {e}")

    # ── اشتراكات Push ──────────────────────────────────────────────────────
    def save_push_subscription(self, user_id: str, subscription: dict) -> bool:
        try:
            with self.get_connection() as conn:
                conn.execute('''
                    INSERT INTO push_subscriptions (user_id, subscription)
                    VALUES (?, ?)
                ''', (str(user_id), json.dumps(subscription)))
            return True
        except Exception as e:
            logger.error(f"save_push_subscription error: {e}")
            return False

    def get_push_subscriptions(self, user_id: str = None) -> list:
        with self.get_connection() as conn:
            if user_id:
                rows = conn.execute(
                    'SELECT * FROM push_subscriptions WHERE user_id = ?', (str(user_id),)
                ).fetchall()
            else:
                rows = conn.execute('SELECT * FROM push_subscriptions').fetchall()
        return [dict(r) for r in rows]

    # ── مزامنة مع GitHub (Abu_Mlk) ──────────────────────────────────────
    def backup_to_github(self, user_id: str):
        """
        حفظ إعدادات مستخدم بعينه إلى GitHub (anwer1230/Abu_Mlk) كنسخة احتياطية دائمة.
        """
        try:
            from github_db import gh_save
            from config import Config
            settings = self.get_all_settings(user_id)
            user     = self.get_user(user_id)
            payload  = {
                "user":      user,
                "settings":  settings,
                "backup_at": datetime.utcnow().isoformat()
            }
            repo_path  = f"db/users/{user_id}/data.json"
            local_path = os.path.join(Config.DATA_DIR, str(user_id), "data.json")
            gh_save(repo_path, local_path, payload,
                    commit_msg=f"💾 نسخة احتياطية — {user_id}")
            logger.info(f"✅ نسخة احتياطية لـ {user_id} رُفعت إلى GitHub")
        except Exception as e:
            logger.warning(f"⚠️ فشل backup_to_github لـ {user_id}: {e}")


# ── Singleton يُستخدم في app.py ──────────────────────────────────────────
_db_instance: Database | None = None


def get_db() -> Database:
    global _db_instance
    if _db_instance is None:
        _db_instance = Database()
    return _db_instance
