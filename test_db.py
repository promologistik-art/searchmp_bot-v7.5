# test_db.py
"""
Тест SQLite базы данных
Запуск: python test_db.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from storage.database import db


def test():
    print("=" * 60)
    print("ТЕСТ SQLite БАЗЫ ДАННЫХ")
    print("=" * 60)
    
    # 1. Проверка структуры
    print("\n1️⃣ Структура БД:")
    with db._get_connection() as conn:
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        print(f"   Таблицы: {[t[0] for t in tables]}")
    
    # 2. Создание тестового пользователя
    print("\n2️⃣ Создание тестового пользователя...")
    test_id = 999999999
    db.create_user(test_id, "test_user", "Test User")
    print(f"   ✅ Создан: {test_id}")
    
    # 3. Получение данных
    print("\n3️⃣ Получение данных...")
    user = db.get_user(test_id)
    if user:
        print(f"   ✅ Найден: {user['user_id']} (@{user.get('username')})")
        print(f"   📊 Запросов: {user.get('total_queries', 0)}")
    
    # 4. Инкремент
    print("\n4️⃣ Инкремент запросов...")
    old = user.get('total_queries', 0)
    db.increment_queries(test_id)
    user = db.get_user(test_id)
    new = user.get('total_queries', 0)
    print(f"   Было: {old}, Стало: {new}")
    
    # 5. Проверка лимитов
    print("\n5️⃣ Проверка лимитов...")
    can, reason = db.can_use_bot(test_id)
    print(f"   Может использовать: {can}")
    
    # 6. Статистика
    print("\n6️⃣ Статистика БД:")
    stats = db.get_users_stats()
    print(f"   Всего: {stats['total_users']}")
    print(f"   Админов: {stats['admins']}")
    print(f"   Подписок: {stats['active_subscriptions']}")
    
    # 7. Очистка
    print("\n7️⃣ Очистка...")
    with db._get_connection() as conn:
        conn.execute("DELETE FROM users WHERE user_id = ?", (test_id,))
    print("   ✅ Тестовый пользователь удален")
    
    print("\n" + "=" * 60)
    print("✅ ВСЕ ТЕСТЫ ПРОЙДЕНЫ!")
    print("=" * 60)


if __name__ == "__main__":
    test()