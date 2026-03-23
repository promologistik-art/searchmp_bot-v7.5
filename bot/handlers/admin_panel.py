# bot/handlers/admin_panel.py
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from config import ADMIN_IDS, ADMIN_USERNAMES, logger
from storage.database import db
from datetime import datetime
import csv
import io


async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Главная панель администратора"""
    user = update.effective_user
    
    # Проверяем права
    is_admin = await _is_admin(user.id, user.username)
    if not is_admin:
        await update.message.reply_text("⛔ Эта команда только для администраторов")
        return
    
    keyboard = [
        [InlineKeyboardButton("👥 Пользователи", callback_data="admin_users")],
        [InlineKeyboardButton("📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton("💾 Экспорт CSV", callback_data="admin_export")],
        [InlineKeyboardButton("🔐 Управление доступом", callback_data="admin_access")],
        [InlineKeyboardButton("❌ Закрыть", callback_data="admin_back")]
    ]
    
    await update.message.reply_text(
        "👑 **Панель администратора**\n\nВыберите действие:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )


async def admin_users_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Список пользователей с пагинацией"""
    query = update.callback_query
    await query.answer()
    
    # Проверяем права
    is_admin = await _is_admin(query.from_user.id, query.from_user.username)
    if not is_admin:
        await query.edit_message_text("⛔ Доступ запрещен")
        return
    
    # Пагинация
    page = 0
    if query.data.startswith("admin_users_"):
        try:
            page = int(query.data.split("_")[2])
        except:
            page = 0
    
    users_per_page = 10
    offset = page * users_per_page
    
    users = db.get_all_users(limit=users_per_page, offset=offset)
    total_users = db.get_users_stats()['total_users']
    total_pages = (total_users + users_per_page - 1) // users_per_page
    
    if not users:
        await query.edit_message_text("📭 Нет пользователей")
        return
    
    text = f"👥 **Пользователи (стр. {page + 1}/{total_pages})**\n\n"
    
    for user in users:
        status_icon = "👑" if user.get('is_admin') else "👤"
        username = user.get('username', 'нет')
        full_name = user.get('full_name', '')[:15]
        total_queries = user.get('total_queries', 0)
        
        text += f"{status_icon} **@{username}**\n"
        text += f"   {full_name} | 📊 {total_queries}\n"
        text += f"   🆔 `{user['user_id']}`\n\n"
    
    # Кнопки пагинации
    keyboard = []
    nav_buttons = []
    
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("◀️ Назад", callback_data=f"admin_users_{page-1}"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("Вперед ▶️", callback_data=f"admin_users_{page+1}"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    keyboard.append([InlineKeyboardButton("🔙 В админ-панель", callback_data="admin_back")])
    
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )


async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Статистика бота"""
    query = update.callback_query
    await query.answer()
    
    # Проверяем права
    is_admin = await _is_admin(query.from_user.id, query.from_user.username)
    if not is_admin:
        await query.edit_message_text("⛔ Доступ запрещен")
        return
    
    # Проверяем истекшие подписки
    db.check_and_expire_subscriptions()
    
    stats = db.get_users_stats()
    
    # Дополнительная статистика по категориям
    from categories import load_cached_categories
    categories = load_cached_categories()
    categories_count = len(categories) if categories else 0
    
    text = (
        "📊 **Статистика бота**\n\n"
        f"👥 Всего пользователей: **{stats['total_users']}**\n"
        f"👑 Администраторов: **{stats['admins']}**\n"
        f"💰 Активных подписок: **{stats['active_subscriptions']}**\n"
        f"⭐ Специальный доступ: **{stats['custom_quota_users']}**\n"
        f"📈 Всего запросов: **{stats['total_queries_all']}**\n\n"
        f"📁 Загружено категорий: **{categories_count}**\n\n"
        f"🆓 Бесплатных запросов: **3** на пользователя\n"
    )
    
    keyboard = [[InlineKeyboardButton("🔙 В админ-панель", callback_data="admin_back")]]
    
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )


async def admin_export_csv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Экспорт пользователей в CSV"""
    query = update.callback_query
    await query.answer()
    
    # Проверяем права
    is_admin = await _is_admin(query.from_user.id, query.from_user.username)
    if not is_admin:
        await query.edit_message_text("⛔ Доступ запрещен")
        return
    
    await query.edit_message_text("📊 Собираю данные для экспорта...")
    
    # Получаем всех пользователей
    users = db.get_all_users(limit=10000)  # Большой лимит
    
    # Создаем CSV
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Заголовки
    writer.writerow([
        'ID', 'Username', 'Имя', 'Дата регистрации', 'Последняя активность',
        'Админ', 'Подписка активна', 'Подписка до', 'Спец. квота',
        'Использовано бесплатных', 'Всего запросов', 'Добавлен кем', 'Добавлен когда'
    ])
    
    for user in users:
        writer.writerow([
            user['user_id'],
            user.get('username', ''),
            user.get('full_name', ''),
            user.get('registered_at', ''),
            user.get('last_activity', ''),
            'Да' if user.get('is_admin') else 'Нет',
            'Да' if user.get('subscription_active') else 'Нет',
            user.get('subscription_until', ''),
            user.get('custom_quota', ''),
            user.get('free_queries_used', 0),
            user.get('total_queries', 0),
            user.get('added_by', ''),
            user.get('added_at', '')
        ])
    
    # Отправляем файл
    output.seek(0)
    await query.message.reply_document(
        document=io.BytesIO(output.getvalue().encode('utf-8-sig')),
        filename=f"users_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        caption=f"📊 Экспорт пользователей ({len(users)} записей)"
    )
    
    # Возвращаемся в админ-панель
    await admin_back(update, context)


async def admin_access_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Меню управления доступом"""
    query = update.callback_query
    await query.answer()
    
    # Проверяем права
    is_admin = await _is_admin(query.from_user.id, query.from_user.username)
    if not is_admin:
        await query.edit_message_text("⛔ Доступ запрещен")
        return
    
    keyboard = [
        [InlineKeyboardButton("➕ Добавить пользователя", callback_data="admin_add_user")],
        [InlineKeyboardButton("📋 Премиум-наборы", callback_data="admin_presets")],
        [InlineKeyboardButton("🔙 Назад", callback_data="admin_back")]
    ]
    
    await query.edit_message_text(
        "🔐 **Управление доступом**\n\n"
        "Выберите действие:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )


async def admin_add_user_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало добавления пользователя"""
    query = update.callback_query
    await query.answer()
    
    # Проверяем права
    is_admin = await _is_admin(query.from_user.id, query.from_user.username)
    if not is_admin:
        await query.edit_message_text("⛔ Доступ запрещен")
        return
    
    # Сохраняем состояние
    context.user_data['admin_action'] = 'waiting_for_username'
    
    await query.edit_message_text(
        "📝 **Добавление пользователя**\n\n"
        "Введите username пользователя (без @) или ID:\n\n"
        "Пример: `john_doe` или `123456789`\n\n"
        "Отправьте /cancel для отмены",
        parse_mode='Markdown'
    )


async def admin_add_preset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Добавление пользователя с пресетом"""
    query = update.callback_query
    await query.answer()
    
    # Проверяем права
    is_admin = await _is_admin(query.from_user.id, query.from_user.username)
    if not is_admin:
        await query.edit_message_text("⛔ Доступ запрещен")
        return
    
    # Сохраняем пресет в контекст
    context.user_data['admin_preset'] = query.data
    
    await query.edit_message_text(
        "📝 **Введите username пользователя**\n\n"
        "Пример: `john_doe` или `123456789`\n\n"
        "Отправьте /cancel для отмены",
        parse_mode='Markdown'
    )


async def admin_add_user_handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ввода username для добавления"""
    user = update.effective_user
    
    # Проверяем права
    is_admin = await _is_admin(user.id, user.username)
    if not is_admin:
        await update.message.reply_text("⛔ Доступ запрещен")
        return
    
    target = update.message.text.strip()
    
    # Ищем пользователя
    user_data = None
    if target.isdigit():
        user_data = db.get_user(int(target))
    else:
        user_data = db.get_user_by_username(target)
    
    if not user_data:
        await update.message.reply_text(
            f"❌ Пользователь {target} не найден.\n"
            f"Попросите его нажать /start и повторите попытку."
        )
        return
    
    user_id = user_data['user_id']
    username = user_data.get('username', target)
    
    # Проверяем, есть ли пресет
    preset = context.user_data.get('admin_preset')
    
    if preset:
        # Применяем пресет
        if preset == "admin_add_admin":
            db.set_user_access(user_id, is_admin=True, added_by=user.username or str(user.id))
            text = f"✅ Пользователь @{username} назначен администратором!"
        elif preset == "admin_add_30_100":
            db.set_user_access(user_id, queries=100, days=30, added_by=user.username or str(user.id))
            text = f"✅ Пользователю @{username} выдано 100 запросов на 30 дней!"
        elif preset == "admin_add_7_50":
            db.set_user_access(user_id, queries=50, days=7, added_by=user.username or str(user.id))
            text = f"✅ Пользователю @{username} выдано 50 запросов на 7 дней!"
        elif preset == "admin_add_365_0":
            db.set_user_access(user_id, queries=0, days=365, added_by=user.username or str(user.id))
            text = f"✅ Пользователю @{username} выдан безлимит на 365 дней!"
        else:
            text = f"⚠️ Неизвестный пресет"
        
        await update.message.reply_text(text)
        
        # Уведомляем пользователя
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"🎉 Вам предоставлен доступ к боту!\n\n{text}\n\nТеперь вы можете использовать бот!"
            )
        except Exception:
            pass
        
        # Очищаем контекст
        context.user_data.pop('admin_preset', None)
        
    else:
        # Ручной ввод
        await update.message.reply_text(
            f"👤 Найден пользователь: @{username}\n\n"
            f"Отправьте команду:\n"
            f"`/add_user @{username} admin` - сделать админом\n"
            f"`/add_user @{username} 100 30` - 100 запросов на 30 дней\n"
            f"`/add_user @{username} 0 30` - безлимит на 30 дней",
            parse_mode='Markdown'
        )


async def admin_back(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Возврат в админ-панель"""
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("👥 Пользователи", callback_data="admin_users")],
        [InlineKeyboardButton("📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton("💾 Экспорт CSV", callback_data="admin_export")],
        [InlineKeyboardButton("🔐 Управление доступом", callback_data="admin_access")],
        [InlineKeyboardButton("❌ Закрыть", callback_data="admin_close")]
    ]
    
    await query.edit_message_text(
        "👑 **Панель администратора**\n\nВыберите действие:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )


async def _is_admin(user_id: int, username: str = None) -> bool:
    """Проверка прав администратора"""
    if user_id in ADMIN_IDS:
        return True
    if username and username in ADMIN_USERNAMES:
        return True
    
    user_data = db.get_user(user_id)
    if user_data and user_data.get('is_admin'):
        return True
    
    return False