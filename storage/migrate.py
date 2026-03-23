# storage/migrate.py
"""
Скрипт миграции из users_database.json в SQLite
Запуск: python -m storage.migrate
"""

import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from storage.database import db
from config import logger


def migrate():
    """Миграция данных"""
    old_json_path = 'users_database.json'
    
    if not os.path.exists(old_json_path):
        logger.info("❌ users_database.json не найден. Миграция не требуется.")
        return True
    
    logger.info("📦 Начинаю миграцию...")
    
    try:
        with open(old_json_path, 'r', encoding='utf-8') as f:
            old_users = json.load(f)
        
        if not old_users:
            logger.info("📭 JSON пуст")
            return True
        
        logger.info(f"👥 Найдено {len(old_users)} пользователей")
        
        migrated = 0
        errors = 0
        
        for user_id_str, data in old_users.items():
            try:
                user_id = int(user_id_str)
                
                existing = db.get_user(user_id)
                
                registered_at = data.get('registered_at') or datetime.now().isoformat()
                last_activity = data.get('last_activity') or datetime.now().isoformat()
                
                if existing:
                    db.update_user(
                        user_id,
                        username=data.get('username'),
                        full_name=data.get('full_name'),
                        last_activity=last_activity,
                        is_admin=data.get('is_admin', False),
                        subscription_active=data.get('subscription_active', False),
                        subscription_until=data.get('subscription_until'),
                        custom_quota=data.get('custom_quota'),
                        free_queries_used=data.get('free_queries_used', 0),
                        total_queries=data.get('total_queries', 0),
                        added_by=data.get('added_by'),
                        added_at=data.get('added_at')
                    )
                else:
                    with db._get_connection() as conn:
                        conn.execute("""
                            INSERT INTO users (
                                user_id, username, full_name, registered_at, last_activity,
                                is_admin, subscription_active, subscription_until,
                                custom_quota, free_queries_used, total_queries,
                                added_by, added_at
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            user_id,
                            data.get('username'),
                            data.get('full_name'),
                            registered_at,
                            last_activity,
                            data.get('is_admin', False),
                            data.get('subscription_active', False),
                            data.get('subscription_until'),
                            data.get('custom_quota'),
                            data.get('free_queries_used', 0),
                            data.get('total_queries', 0),
                            data.get('added_by'),
                            data.get('added_at')
                        ))
                
                migrated += 1
                logger.info(f"✅ Мигрирован: {user_id} (@{data.get('username', '')})")
                
            except Exception as e:
                errors += 1
                logger.error(f"❌ Ошибка {user_id_str}: {e}")
        
        # Бэкап старого файла
        backup = f"{old_json_path}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        os.rename(old_json_path, backup)
        logger.info(f"📁 Бэкап: {backup}")
        
        logger.info(f"\n✅ Миграция завершена! Успешно: {migrated}, Ошибок: {errors}")
        
        stats = db.get_users_stats()
        logger.info(f"📊 Статистика: {stats['total_users']} пользователей")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
        return False


if __name__ == "__main__":
    print("=" * 60)
    print("МИГРАЦИЯ JSON → SQLITE")
    print("=" * 60)
    migrate()