# storage/database_sqlite.py
"""
SQLite версия базы данных
Используется вместо JSON для лучшей производительности
"""

import sqlite3
import json
import os
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
from contextlib import contextmanager

from config import logger

# Путь к SQLite БД (в shared хранилище)
from config import SHARED_DIR
DATABASE_PATH = os.path.join(SHARED_DIR, 'database', 'users.db')


class DatabaseSQLite:
    """SQLite реализация базы данных"""
    
    def __init__(self):
        self.db_path = DATABASE_PATH
        self._init_db()
    
    @contextmanager
    def _get_connection(self):
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Database error: {e}")
            raise
        finally:
            conn.close()
    
    def _init_db(self):
        """Создание таблиц"""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        
        with self._get_connection() as conn:
            # Таблица пользователей
            conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    full_name TEXT,
                    registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_activity TIMESTAMP,
                    is_admin BOOLEAN DEFAULT 0,
                    subscription_active BOOLEAN DEFAULT 0,
                    subscription_until TIMESTAMP,
                    custom_quota INTEGER,
                    free_queries_used INTEGER DEFAULT 0,
                    free_queries_total INTEGER DEFAULT 3,
                    total_queries INTEGER DEFAULT 0,
                    added_by TEXT,
                    added_at TIMESTAMP
                )
            """)
            
            # Таблица истории запросов
            conn.execute("""
                CREATE TABLE IF NOT EXISTS query_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    category TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(user_id) REFERENCES users(user_id)
                )
            """)
            
            # Таблица просмотренных категорий
            conn.execute("""
                CREATE TABLE IF NOT EXISTS viewed_categories (
                    user_id INTEGER,
                    category_path TEXT,
                    viewed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (user_id, category_path)
                )
            """)
            
            # Индексы
            conn.execute("CREATE INDEX IF NOT EXISTS idx_username ON users(username)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_user_queries ON query_history(user_id)")
            
            logger.info("✅ SQLite database initialized")
    
    # === ОСНОВНЫЕ МЕТОДЫ (совместимые со старым API) ===
    
    def get_user_data(self, user_id: int) -> Dict:
        """Получить данные пользователя (как в старой JSON версии)"""
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            
            if row:
                return dict(row)
            else:
                # Создаем нового пользователя
                now = datetime.now().isoformat()
                with self._get_connection() as conn2:
                    conn2.execute("""
                        INSERT INTO users (user_id, registered_at, last_activity)
                        VALUES (?, ?, ?)
                    """, (user_id, now, now))
                
                return {
                    'user_id': user_id,
                    'username': None,
                    'full_name': None,
                    'registered_at': now,
                    'last_activity': now,
                    'is_admin': False,
                    'subscription_active': False,
                    'subscription_until': None,
                    'custom_quota': None,
                    'free_queries_used': 0,
                    'free_queries_total': 3,
                    'total_queries': 0,
                    'added_by': None,
                    'added_at': None
                }
    
    def update_user_data(self, user_id: int, data: Dict):
        """Обновить данные пользователя"""
        with self._get_connection() as conn:
            for key, value in data.items():
                if key in ['user_id']:
                    continue
                try:
                    conn.execute(
                        f"UPDATE users SET {key} = ? WHERE user_id = ?",
                        (value, user_id)
                    )
                except Exception as e:
                    logger.error(f"Error updating {key}: {e}")
    
    def update_user_info(self, user_id: int, username: str, full_name: str):
        """Обновить информацию о пользователе"""
        now = datetime.now().isoformat()
        with self._get_connection() as conn:
            conn.execute("""
                UPDATE users 
                SET username = ?, full_name = ?, last_activity = ?
                WHERE user_id = ?
            """, (username, full_name, now, user_id))
    
    def can_use_bot(self, user_id: int, admin_ids: list, admin_usernames: list, username: str):
        """Проверить, может ли пользователь использовать бота"""
        user = self.get_user_data(user_id)
        
        # Проверка админов
        if user_id in admin_ids:
            return True, "admin_by_id"
        if username and username in admin_usernames:
            return True, "admin_by_username"
        if user.get('is_admin'):
            return True, "admin_by_db"
        
        # Проверка специальной квоты
        custom_quota = user.get('custom_quota')
        if custom_quota:
            free_used = user.get('free_queries_used', 0)
            if free_used < custom_quota:
                return True, f"custom ({free_used + 1}/{custom_quota})"
            return False, "custom_limit_exceeded"
        
        # Проверка подписки
        if user.get('subscription_active'):
            sub_until = user.get('subscription_until')
            if sub_until:
                try:
                    sub_date = datetime.fromisoformat(sub_until)
                    if sub_date > datetime.now():
                        return True, "subscribed"
                except:
                    pass
        
        # Бесплатные запросы
        free_used = user.get('free_queries_used', 0)
        free_total = user.get('free_queries_total', 3)
        
        if free_used < free_total:
            return True, f"free ({free_used + 1}/{free_total})"
        
        return False, "limit_exceeded"
    
    def increment_query_count(self, user_id: int, admin_ids: list, admin_usernames: list, username: str):
        """Увеличить счетчик запросов"""
        user = self.get_user_data(user_id)
        
        # Админы не тратят запросы
        if user_id in admin_ids or (username and username in admin_usernames) or user.get('is_admin'):
            with self._get_connection() as conn:
                conn.execute("""
                    UPDATE users 
                    SET total_queries = total_queries + 1,
                        last_activity = ?
                    WHERE user_id = ?
                """, (datetime.now().isoformat(), user_id))
            return
        
        # Обычные пользователи
        custom_quota = user.get('custom_quota')
        if custom_quota:
            used = user.get('free_queries_used', 0)
            if used < custom_quota:
                with self._get_connection() as conn:
                    conn.execute("""
                        UPDATE users 
                        SET free_queries_used = free_queries_used + 1,
                            total_queries = total_queries + 1,
                            last_activity = ?
                        WHERE user_id = ?
                    """, (datetime.now().isoformat(), user_id))
        else:
            # Проверяем подписку
            if user.get('subscription_active'):
                sub_until = user.get('subscription_until')
                if sub_until:
                    try:
                        sub_date = datetime.fromisoformat(sub_until)
                        if sub_date > datetime.now():
                            # По подписке не увеличиваем счетчик
                            with self._get_connection() as conn:
                                conn.execute("""
                                    UPDATE users 
                                    SET total_queries = total_queries + 1,
                                        last_activity = ?
                                    WHERE user_id = ?
                                """, (datetime.now().isoformat(), user_id))
                            return
                    except:
                        pass
            
            # Бесплатные запросы
            free_used = user.get('free_queries_used', 0)
            free_total = user.get('free_queries_total', 3)
            if free_used < free_total:
                with self._get_connection() as conn:
                    conn.execute("""
                        UPDATE users 
                        SET free_queries_used = free_queries_used + 1,
                            total_queries = total_queries + 1,
                            last_activity = ?
                        WHERE user_id = ?
                    """, (datetime.now().isoformat(), user_id))
    
    def set_user_access(self, user_id: int, queries: int = None, days: int = None, 
                        is_admin: bool = False, added_by: str = None):
        """Установить доступ пользователя"""
        now = datetime.now().isoformat()
        
        with self._get_connection() as conn:
            if is_admin:
                conn.execute("""
                    UPDATE users 
                    SET is_admin = 1, 
                        custom_quota = NULL,
                        subscription_active = 0,
                        added_by = ?,
                        added_at = ?
                    WHERE user_id = ?
                """, (added_by, now, user_id))
            elif queries is not None:
                if queries == 0:
                    queries_val = 999999
                else:
                    queries_val = queries
                
                conn.execute("""
                    UPDATE users 
                    SET custom_quota = ?,
                        free_queries_used = 0,
                        is_admin = 0,
                        added_by = ?,
                        added_at = ?
                    WHERE user_id = ?
                """, (queries_val, added_by, now, user_id))
                
                if days:
                    until = (datetime.now() + timedelta(days=days)).isoformat()
                    conn.execute("""
                        UPDATE users 
                        SET subscription_active = 1,
                            subscription_until = ?
                        WHERE user_id = ?
                    """, (until, user_id))
    
    def get_user_by_username(self, username: str):
        """Найти пользователя по username"""
        username = username.replace('@', '').lower()
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM users WHERE LOWER(username) = ?",
                (username,)
            )
            row = cursor.fetchone()
            if row:
                return row['user_id'], dict(row)
            return None, None
    
    def get_all_users(self) -> Dict:
        """Получить всех пользователей (для совместимости)"""
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM users ORDER BY registered_at DESC")
            users = {}
            for row in cursor.fetchall():
                users[str(row['user_id'])] = dict(row)
            return users
    
    def get_users_stats(self) -> Dict:
        """Получить статистику"""
        with self._get_connection() as conn:
            cursor = conn.execute("""
                SELECT 
                    COUNT(*) as total_users,
                    SUM(CASE WHEN is_admin = 1 THEN 1 ELSE 0 END) as admins,
                    SUM(CASE WHEN subscription_active = 1 THEN 1 ELSE 0 END) as active_subscriptions,
                    SUM(CASE WHEN custom_quota IS NOT NULL AND custom_quota < 999999 THEN 1 ELSE 0 END) as custom_quota_users
                FROM users
            """)
            row = cursor.fetchone()
            return dict(row)
    
    def add_query_record(self, user_id: int, category: str):
        """Добавить запись о запросе"""
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO query_history (user_id, category)
                VALUES (?, ?)
            """, (user_id, category))
    
    def add_viewed_category(self, user_id: int, category_path: str):
        """Добавить просмотренную категорию"""
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO viewed_categories (user_id, category_path)
                VALUES (?, ?)
            """, (user_id, category_path))
    
    def get_viewed_categories(self, user_id: int) -> set:
        """Получить просмотренные категории"""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT category_path FROM viewed_categories WHERE user_id = ?",
                (user_id,)
            )
            return {row['category_path'] for row in cursor.fetchall()}
    
    def migrate_from_json(self, json_path: str = 'users_database.json'):
        """Миграция из JSON файла"""
        import json
        if not os.path.exists(json_path):
            logger.info("JSON файл не найден")
            return
        
        with open(json_path, 'r', encoding='utf-8') as f:
            old_users = json.load(f)
        
        for user_id_str, data in old_users.items():
            user_id = int(user_id_str)
            self.update_user_data(user_id, {
                'username': data.get('username'),
                'full_name': data.get('full_name'),
                'registered_at': data.get('registered_at'),
                'last_activity': data.get('last_activity'),
                'is_admin': data.get('is_admin', False),
                'subscription_active': data.get('subscription_active', False),
                'subscription_until': data.get('subscription_until'),
                'custom_quota': data.get('custom_quota'),
                'free_queries_used': data.get('free_queries_used', 0),
                'total_queries': data.get('total_queries', 0),
                'added_by': data.get('added_by'),
                'added_at': data.get('added_at')
            })
        
        logger.info(f"Мигрировано {len(old_users)} пользователей")


# Создаем глобальный экземпляр
db = DatabaseSQLite()