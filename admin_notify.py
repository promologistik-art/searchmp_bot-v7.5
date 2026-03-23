# admin_notify.py
from telegram import Update
from telegram.ext import ContextTypes
from config import ADMIN_IDS, ADMIN_USERNAMES, logger
from storage.database import db
from datetime import datetime


async def notify_admin_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Уведомляет админа о новом пользователе"""
    user = update.effective_user
    user_id = user.id
    username = user.username or "нет username"
    first_name = user.first_name or ""
    last_name = user.last_name or ""
    full_name = f"{first_name} {last_name}".strip()

    # Проверяем, существует ли пользователь
    existing = db.get_user(user_id)
    
    if not existing:
        # Создаем нового пользователя
        db.create_user(user_id, username, full_name)
        logger.info(f"✅ Новый пользователь: {user_id} (@{username})")
    else:
        # Обновляем информацию
        db.update_user(user_id, username=username, full_name=full_name)
        logger.info(f"🔄 Обновлен пользователь: {user_id} (@{username})")
    
    user_data = db.get_user(user_id)
    if not user_data:
        return
    
    free_used = user_data.get('free_queries_used', 0)
    free_total = user_data.get('free_queries_total', 3)
    total_queries = user_data.get('total_queries', 0)
    custom_quota = user_data.get('custom_quota')
    is_admin = user_data.get('is_admin', False)
    subscription_active = user_data.get('subscription_active', False)

    status = "🆓 Бесплатный"
    if is_admin:
        status = "👑 Админ"
    elif subscription_active:
        subscription_until = user_data.get('subscription_until')
        if subscription_until:
            until_date = datetime.fromisoformat(subscription_until)
            days_left = (until_date - datetime.now()).days
            status = f"💰 Подписка (до {until_date.strftime('%d.%m.%Y')}, {days_left} дн.)"
        else:
            status = "💰 Подписка"
    elif custom_quota:
        remaining = custom_quota - free_used
        status = f"⭐ Спец. доступ (осталось {remaining}/{custom_quota})"

    message = (
        f"👋 **Новый пользователь нажал /start**\n\n"
        f"📱 Username: @{username}\n"
        f"🆔 ID: `{user_id}`\n"
        f"👤 Имя: {full_name}\n"
        f"📊 Статус: {status}\n"
        f"📈 Всего запросов: {total_queries}"
    )

    # Отправляем уведомление всем админам
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text=message,
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Не удалось отправить уведомление админу {admin_id}: {e}")


async def notify_admin_analyze(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Уведомляет админа о запуске анализа"""
    user = update.effective_user
    user_id = user.id
    username = user.username or "нет username"

    user_data = db.get_user(user_id)
    if not user_data:
        return
    
    free_used = user_data.get('free_queries_used', 0)
    free_total = user_data.get('free_queries_total', 3)
    total_queries = user_data.get('total_queries', 0)
    custom_quota = user_data.get('custom_quota')
    is_admin = user_data.get('is_admin', False)

    # Получаем выбранные категории
    selected = context.user_data.get('selected', [])
    categories_count = len(selected)

    status = "👑" if is_admin else "👤"
    quota_info = ""
    if custom_quota and not is_admin:
        remaining = custom_quota - free_used
        quota_info = f" (осталось: {remaining}/{custom_quota})"

    message = (
        f"🚀 **Пользователь запустил анализ**\n\n"
        f"{status} Username: @{username}\n"
        f"🆔 ID: `{user_id}`\n"
        f"📊 Категорий: {categories_count}\n"
        f"🔢 Использовано: {free_used}/{free_total}{quota_info}\n"
        f"📈 Всего: {total_queries}"
    )

    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text=message,
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Не удалось отправить уведомление админу {admin_id}: {e}")


async def add_user_access(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Добавляет пользователя с доступом (команда /add_user)"""
    user = update.effective_user

    # Проверяем, что вызывающий - админ
    is_admin = False
    if user.id in ADMIN_IDS:
        is_admin = True
    elif user.username and user.username in ADMIN_USERNAMES:
        is_admin = True
    else:
        user_data = db.get_user(user.id)
        if user_data and user_data.get('is_admin', False):
            is_admin = True

    if not is_admin:
        await update.message.reply_text("❌ У вас нет прав администратора")
        return

    # Получаем параметры из команды
    try:
        args = context.args
        if len(args) < 1:
            await update.message.reply_text(
                "❌ Использование:\n"
                "• /add_user @username admin - сделать админом\n"
                "• /add_user @username 100 30 - 100 запросов на 30 дней\n"
                "• /add_user @username 100 - 100 запросов бессрочно\n"
                "• /add_user @username 0 30 - безлимит на 30 дней"
            )
            return

        target_username = args[0].replace('@', '')
        
        # Ищем пользователя в БД
        user_data = db.get_user_by_username(target_username)
        
        if not user_data:
            await update.message.reply_text(
                f"⚠️ Пользователь @{target_username} еще не запускал бота.\n"
                f"Попросите его нажать /start, затем повторите команду."
            )
            return
        
        user_id = user_data['user_id']
        
        # Обработка параметров
        if len(args) >= 2 and args[1].lower() == 'admin':
            # Делаем админом
            db.set_user_access(user_id, is_admin=True, added_by=user.username or str(user.id))
            
            await update.message.reply_text(
                f"✅ Пользователь @{target_username} теперь администратор!"
            )
            
            # Уведомляем пользователя
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text="🎉 Вам назначены права администратора!\nТеперь у вас неограниченный доступ к боту."
                )
            except Exception:
                await update.message.reply_text(
                    f"⚠️ Не удалось отправить уведомление пользователю."
                )
        
        elif len(args) >= 2:
            try:
                queries = int(args[1])
                days = int(args[2]) if len(args) > 2 else None
                
                db.set_user_access(user_id, queries=queries, days=days, 
                                  added_by=user.username or str(user.id))
                
                days_text = f" на {days} дней" if days else " бессрочно"
                quota_text = "безлимит" if queries == 0 else f"{queries} запросов"
                
                await update.message.reply_text(
                    f"✅ Доступ для @{target_username} установлен!\n"
                    f"📊 Лимит: {quota_text}\n"
                    f"📅 Срок: {days_text}"
                )
                
                # Уведомляем пользователя
                try:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=(
                            f"🎉 Вам предоставлен доступ к боту!\n"
                            f"📊 Лимит: {quota_text}\n"
                            f"📅 Срок: {days_text}\n\n"
                            f"Теперь вы можете использовать бот!"
                        )
                    )
                except Exception:
                    await update.message.reply_text(
                        f"⚠️ Не удалось отправить уведомление пользователю."
                    )
                    
            except ValueError:
                await update.message.reply_text("❌ Количество запросов и дней должны быть числами")
        else:
            await update.message.reply_text("❌ Укажите параметры доступа или 'admin'")

    except Exception as e:
        logger.error(f"Ошибка в add_user_access: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")


async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает список пользователей"""
    user = update.effective_user

    # Проверяем права
    is_admin = False
    if user.id in ADMIN_IDS:
        is_admin = True
    elif user.username and user.username in ADMIN_USERNAMES:
        is_admin = True
    else:
        user_data = db.get_user(user.id)
        if user_data and user_data.get('is_admin', False):
            is_admin = True

    if not is_admin:
        await update.message.reply_text("❌ У вас нет прав администратора")
        return

    users = db.get_all_users(limit=50)
    stats = db.get_users_stats()

    text = (
        f"📊 **Статистика бота**\n\n"
        f"👥 Всего пользователей: {stats['total_users']}\n"
        f"👑 Админов: {stats['admins']}\n"
        f"💰 Активных подписок: {stats['active_subscriptions']}\n"
        f"⭐ Спец. доступ: {stats['custom_quota_users']}\n"
        f"📈 Всего запросов: {stats['total_queries_all']}\n\n"
        f"**Последние пользователи:**\n\n"
    )

    for user_data in users:
        username = user_data.get('username', 'нет')
        full_name = user_data.get('full_name', '')[:20]
        registered = user_data.get('registered_at', '')[:10] if user_data.get('registered_at') else '?'
        free_used = user_data.get('free_queries_used', 0)
        custom_quota = user_data.get('custom_quota')
        total = user_data.get('total_queries', 0)

        status = "🆓"
        if user_data.get('is_admin'):
            status = "👑"
        elif user_data.get('subscription_active'):
            status = "💰"
        elif custom_quota:
            remaining = custom_quota - free_used
            status = f"⭐ {remaining}/{custom_quota}"

        text += f"{status} @{username} | {full_name}\n"
        text += f"   📅 {registered} | 📊 всего: {total}\n\n"

        if len(text) > 3500:  # Telegram лимит
            text += "\n... и другие"
            break

    await update.message.reply_text(text, parse_mode='Markdown')


async def user_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает информацию о пользователе"""
    user = update.effective_user

    # Проверяем права
    is_admin = False
    if user.id in ADMIN_IDS:
        is_admin = True
    elif user.username and user.username in ADMIN_USERNAMES:
        is_admin = True
    else:
        user_data = db.get_user(user.id)
        if user_data and user_data.get('is_admin', False):
            is_admin = True

    if not is_admin:
        await update.message.reply_text("❌ У вас нет прав администратора")
        return

    try:
        args = context.args
        if not args:
            await update.message.reply_text("❌ Укажите @username или ID пользователя")
            return

        target = args[0]
        user_data = None
        
        if target.startswith('@'):
            # Поиск по username
            user_data = db.get_user_by_username(target[1:])
        else:
            # Поиск по ID
            try:
                user_id = int(target)
                user_data = db.get_user(user_id)
            except ValueError:
                pass

        if not user_data:
            await update.message.reply_text(f"❌ Пользователь {target} не найден")
            return

        # Формируем информацию
        registered = user_data.get('registered_at', 'Неизвестно')[:16] if user_data.get('registered_at') else 'Неизвестно'
        last_activity = user_data.get('last_activity', 'Нет')[:16] if user_data.get('last_activity') else 'Нет'
        free_used = user_data.get('free_queries_used', 0)
        free_total = user_data.get('free_queries_total', 3)
        total_queries = user_data.get('total_queries', 0)
        custom_quota = user_data.get('custom_quota')
        is_admin_user = user_data.get('is_admin', False)
        subscription_active = user_data.get('subscription_active', False)
        subscription_until = user_data.get('subscription_until', '')
        added_by = user_data.get('added_by', '—')
        added_at = user_data.get('added_at', '—')[:10] if user_data.get('added_at') else '—'

        status = "🆓 Бесплатный"
        quota_info = ""
        if is_admin_user:
            status = "👑 Администратор"
        elif subscription_active and subscription_until:
            until_date = datetime.fromisoformat(subscription_until)
            if until_date > datetime.now():
                days_left = (until_date - datetime.now()).days
                status = f"💰 Подписка"
                quota_info = f" (до {until_date.strftime('%d.%m.%Y')}, осталось {days_left} дн.)"
            else:
                status = "💰 Подписка (истекла)"
        elif custom_quota:
            remaining = custom_quota - free_used
            status = f"⭐ Спец. доступ"
            quota_info = f" (осталось {remaining}/{custom_quota})"

        text = (
            f"📱 **Информация о пользователе**\n\n"
            f"🆔 ID: `{user_data['user_id']}`\n"
            f"👤 Username: @{user_data.get('username', 'нет')}\n"
            f"👤 Имя: {user_data.get('full_name', 'неизвестно')}\n"
            f"📊 Статус: {status}{quota_info}\n"
            f"📅 Зарегистрирован: {registered}\n"
            f"⏳ Последняя активность: {last_activity}\n"
            f"🔢 Использовано: {free_used}/{free_total} (бесплатных)\n"
            f"📈 Всего запросов: {total_queries}\n"
        )

        if added_by != '—':
            text += f"➕ Добавлен: {added_by} ({added_at})\n"

        await update.message.reply_text(text, parse_mode='Markdown')

    except Exception as e:
        logger.error(f"Ошибка в user_info: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")