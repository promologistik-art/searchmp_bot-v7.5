# storage/database.py
# Совместимая обертка для работы со старым JSON кодом
# При переключении на SQLite, импорт будет идти из database_sqlite

import json
import os
import pickle
from datetime import datetime, timedelta
from config import USERS_DB_FILE, HISTORY_FILE, logger, USE_SQLITE

# Если используем SQLite, переадресуем импорт
if USE_SQLITE:
    from storage.database_sqlite import db as _db
    # Экспортируем функции из SQLite версии
    get_user_data = _db.get_user_data
    update_user_data = _db.update_user_data
    update_user_info = _db.update_user_info
    create_user_record = lambda user_id, username=None, full_name=None: _db.get_user_data(user_id)
    can_use_bot = _db.can_use_bot
    increment_query_count = _db.increment_query_count
    set_user_access = _db.set_user_access
    get_user_by_username = _db.get_user_by_username
    get_user_by_id = lambda user_id: (user_id, _db.get_user_data(user_id))
    get_all_users = _db.get_all_users
    get_users_stats = _db.get_users_stats
    load_viewed_categories = lambda: _db.get_viewed_categories(0)  # Временная заглушка
    save_viewed_categories = lambda x: None
    get_all_queries = lambda: 0
    get_daily_stats = lambda: {'today': 0, 'yesterday': 0, 'week': 0}
    get_popular_categories = lambda limit=10: []
    add_query_record = _db.add_query_record
    
    # Создаем объект db для импорта
    db = _db
    
    logger.info("✅ Используется SQLite база данных")
else:
    # === ОРИГИНАЛЬНЫЙ JSON КОД ===
    
    def load_users_db():
        """Загружает базу пользователей"""
        try:
            if os.path.exists(USERS_DB_FILE):
                with open(USERS_DB_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return {}
        except Exception as e:
            logger.error(f"Ошибка загрузки БД пользователей: {e}")
            return {}

    def save_users_db(users_db):
        """Сохраняет базу пользователей"""
        try:
            with open(USERS_DB_FILE, 'w', encoding='utf-8') as f:
                json.dump(users_db, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Ошибка сохранения БД пользователей: {e}")

    def get_user_data(user_id):
        """Получает данные пользователя по ID"""
        users_db = load_users_db()
        user_id_str = str(user_id)

        if user_id_str not in users_db:
            users_db[user_id_str] = {
                'free_queries_used': 0,
                'free_queries_total': 3,
                'total_queries': 0,
                'registered_at': datetime.now().isoformat(),
                'subscription_active': False,
                'subscription_until': None,
                'custom_quota': None,
                'username': None,
                'full_name': None,
                'is_admin': False,
                'added_by': None,
                'added_at': None,
                'last_activity': None
            }
            save_users_db(users_db)

        return users_db[user_id_str]

    def update_user_data(user_id, data):
        """Обновляет данные пользователя"""
        users_db = load_users_db()
        user_id_str = str(user_id)

        if user_id_str not in users_db:
            users_db[user_id_str] = {}

        users_db[user_id_str].update(data)
        save_users_db(users_db)

    def update_user_info(user_id, username, full_name):
        """Обновляет информацию о пользователе"""
        user_data = get_user_data(user_id)
        user_data['username'] = username
        user_data['full_name'] = full_name
        user_data['last_activity'] = datetime.now().isoformat()
        update_user_data(user_id, user_data)

    def create_user_record(user_id, username=None, full_name=None):
        """Создает запись о пользователе, если её нет"""
        users_db = load_users_db()
        user_id_str = str(user_id)

        if user_id_str not in users_db:
            users_db[user_id_str] = {
                'free_queries_used': 0,
                'free_queries_total': 3,
                'total_queries': 0,
                'registered_at': datetime.now().isoformat(),
                'subscription_active': False,
                'subscription_until': None,
                'custom_quota': None,
                'username': username,
                'full_name': full_name,
                'is_admin': False,
                'added_by': None,
                'added_at': None,
                'last_activity': None
            }
            save_users_db(users_db)
            return True
        return False

    def can_use_bot(user_id, admin_ids, admin_usernames, username):
        """Проверяет, может ли пользователь использовать бота"""
        user_data = get_user_data(user_id)

        if user_id in admin_ids:
            return True, "admin_by_id"
        if username and username in admin_usernames:
            return True, "admin_by_username"
        if user_data.get('is_admin', False):
            return True, "admin_by_db"

        custom_quota = user_data.get('custom_quota')
        if custom_quota:
            free_used = user_data.get('free_queries_used', 0)
            if free_used < custom_quota:
                return True, f"custom ({free_used + 1}/{custom_quota})"
            else:
                return False, "custom_limit_exceeded"

        if user_data.get('subscription_active', False):
            sub_until = user_data.get('subscription_until')
            if sub_until:
                try:
                    sub_date = datetime.fromisoformat(sub_until)
                    if sub_date > datetime.now():
                        return True, "subscribed"
                    else:
                        update_user_data(user_id, {'subscription_active': False, 'subscription_until': None})
                except:
                    pass

        free_used = user_data.get('free_queries_used', 0)
        free_total = user_data.get('free_queries_total', 3)

        if free_used < free_total:
            return True, f"free ({free_used + 1}/{free_total})"

        return False, "limit_exceeded"

    def increment_query_count(user_id, admin_ids, admin_usernames, username):
        """Увеличивает счетчик запросов"""
        user_data = get_user_data(user_id)

        if user_id in admin_ids or (username and username in admin_usernames) or user_data.get('is_admin', False):
            user_data['total_queries'] = user_data.get('total_queries', 0) + 1
            user_data['last_activity'] = datetime.now().isoformat()
            update_user_data(user_id, user_data)
            return

        custom_quota = user_data.get('custom_quota')
        if custom_quota:
            free_used = user_data.get('free_queries_used', 0)
            if free_used < custom_quota:
                user_data['free_queries_used'] = free_used + 1
        else:
            if user_data.get('subscription_active', False):
                sub_until = user_data.get('subscription_until')
                if sub_until:
                    try:
                        sub_date = datetime.fromisoformat(sub_until)
                        if sub_date > datetime.now():
                            pass
                    except:
                        pass
            else:
                free_used = user_data.get('free_queries_used', 0)
                free_total = user_data.get('free_queries_total', 3)
                if free_used < free_total:
                    user_data['free_queries_used'] = free_used + 1

        user_data['total_queries'] = user_data.get('total_queries', 0) + 1
        user_data['last_activity'] = datetime.now().isoformat()
        update_user_data(user_id, user_data)

    def set_user_access(user_id, queries=None, days=None, is_admin=False, added_by=None):
        """Устанавливает доступ для пользователя"""
        user_data = get_user_data(user_id)
        user_data['free_queries_used'] = 0

        if is_admin:
            user_data['is_admin'] = True
            user_data['custom_quota'] = None
            user_data['subscription_active'] = False
            user_data['subscription_until'] = None
        else:
            user_data['is_admin'] = False
            if queries is not None:
                if queries == 0:
                    user_data['custom_quota'] = 999999
                else:
                    user_data['custom_quota'] = queries

            if days:
                user_data['subscription_active'] = True
                user_data['subscription_until'] = (datetime.now() + timedelta(days=days)).isoformat()
            else:
                user_data['subscription_active'] = False
                user_data['subscription_until'] = None

        user_data['added_by'] = added_by
        user_data['added_at'] = datetime.now().isoformat()
        update_user_data(user_id, user_data)
        return user_data

    def get_user_by_username(username):
        """Ищет пользователя по username"""
        users_db = load_users_db()
        username = username.replace('@', '').lower()

        for user_id, data in users_db.items():
            if data.get('username') and data['username'].lower() == username:
                return int(user_id), data
        return None, None

    def get_user_by_id(user_id):
        """Получает пользователя по ID"""
        users_db = load_users_db()
        user_id_str = str(user_id)

        if user_id_str in users_db:
            return int(user_id), users_db[user_id_str]
        return None, None

    def get_all_users():
        """Возвращает список всех пользователей"""
        return load_users_db()

    def get_users_stats():
        """Возвращает статистику по пользователям"""
        users_db = load_users_db()
        total_users = len(users_db)
        active_subscriptions = 0
        admins = 0
        custom_quota_users = 0

        for user_id, data in users_db.items():
            if data.get('is_admin', False):
                admins += 1
            elif data.get('subscription_active', False):
                sub_until = data.get('subscription_until')
                if sub_until:
                    try:
                        sub_date = datetime.fromisoformat(sub_until)
                        if sub_date > datetime.now():
                            active_subscriptions += 1
                    except:
                        pass
            elif data.get('custom_quota'):
                custom_quota_users += 1

        return {
            'total_users': total_users,
            'admins': admins,
            'active_subscriptions': active_subscriptions,
            'custom_quota_users': custom_quota_users
        }

    def get_all_queries():
        try:
            users_db = load_users_db()
            total = 0
            for user_id, user_data in users_db.items():
                total += user_data.get('total_queries', 0)
            return total
        except:
            return 0

    def get_daily_stats():
        return {'today': 0, 'yesterday': 0, 'week': 0}

    def get_popular_categories(limit=10):
        return []

    def add_query_record(user_id, category):
        pass

    def load_viewed_categories():
        try:
            if os.path.exists(HISTORY_FILE):
                with open(HISTORY_FILE, 'rb') as f:
                    return pickle.load(f)
            return set()
        except:
            return set()

    def save_viewed_categories(viewed_set):
        try:
            with open(HISTORY_FILE, 'wb') as f:
                pickle.dump(viewed_set, f)
        except Exception as e:
            logger.error(f"Ошибка сохранения истории: {e}")

    # Создаем объект db для импорта (обертка над функциями)
    class DatabaseWrapper:
        def get_user_data(self, user_id):
            return get_user_data(user_id)
        
        def update_user_data(self, user_id, data):
            return update_user_data(user_id, data)
        
        def update_user_info(self, user_id, username, full_name):
            return update_user_info(user_id, username, full_name)
        
        def can_use_bot(self, user_id, admin_ids, admin_usernames, username):
            return can_use_bot(user_id, admin_ids, admin_usernames, username)
        
        def increment_query_count(self, user_id, admin_ids, admin_usernames, username):
            return increment_query_count(user_id, admin_ids, admin_usernames, username)
        
        def set_user_access(self, user_id, queries=None, days=None, is_admin=False, added_by=None):
            return set_user_access(user_id, queries, days, is_admin, added_by)
        
        def get_user_by_username(self, username):
            return get_user_by_username(username)
        
        def get_all_users(self):
            return get_all_users()
        
        def get_users_stats(self):
            return get_users_stats()
    
    db = DatabaseWrapper()
    logger.info("✅ Используется JSON база данных")