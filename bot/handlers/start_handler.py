# bot/handlers/start_handler.py (ключевые функции)
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from storage.database import db
from admin_notify import notify_admin_start
import logging

logger = logging.getLogger(__name__)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    user = update.effective_user
    
    # Создаем или обновляем пользователя
    existing = db.get_user(user.id)
    
    if not existing:
        full_name = f"{user.first_name or ''} {user.last_name or ''}".strip()
        db.create_user(user.id, user.username, full_name)
        
        # Уведомляем админов
        await notify_admin_start(update, context)
        
        welcome_text = (
            f"🎉 **Добро пожаловать, {user.first_name or 'пользователь'}!**\n\n"
            f"🤖 Я помогу вам найти товары для продажи на Ozon.\n\n"
            f"✅ **У вас 3 бесплатных запроса** для знакомства с ботом.\n\n"
            f"📋 **Что я умею:**\n"
            f"• Анализировать категории товаров\n"
            f"• Рассчитывать комиссии и логистику\n"
            f"• Создавать готовые Excel-отчеты с формулами\n\n"
            f"🔧 **Начните с настройки:** /criteria\n"
            f"📊 **Выберите категории:** /list\n"
            f"💡 **Помощь:** /help"
        )
    else:
        # Обновляем активность
        db.update_activity(user.id)
        
        welcome_text = (
            f"🎉 **С возвращением, {user.first_name or 'пользователь'}!**\n\n"
            f"📊 У вас осталось **{await _get_queries_left(user.id)}** запросов.\n\n"
            f"🔧 **Настройка:** /criteria\n"
            f"📋 **Категории:** /list\n"
            f"📤 **Свои категории:** /upload\n"
            f"📊 **Статус:** /status"
        )
    
    keyboard = [
        [InlineKeyboardButton("🔧 Настроить критерии", callback_data="do_criteria")],
        [InlineKeyboardButton("📋 Выбрать категории", callback_data="do_list")],
        [InlineKeyboardButton("📤 Загрузить свои категории", callback_data="do_upload")],
        [InlineKeyboardButton("📊 Мой статус", callback_data="do_status")]
    ]
    
    await update.message.reply_text(
        welcome_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /status - статус пользователя"""
    user = update.effective_user
    user_data = db.get_user(user.id)
    
    if not user_data:
        await update.message.reply_text("❌ Ошибка: пользователь не найден")
        return
    
    free_used = user_data.get('free_queries_used', 0)
    free_total = user_data.get('free_queries_total', 3)
    total_queries = user_data.get('total_queries', 0)
    custom_quota = user_data.get('custom_quota')
    is_admin = user_data.get('is_admin', False)
    subscription_active = user_data.get('subscription_active', False)
    subscription_until = user_data.get('subscription_until')
    
    # Определяем статус
    if is_admin:
        status_text = "👑 **Администратор**\n🔓 Безлимитный доступ"
        queries_left = "∞"
    elif subscription_active and subscription_until:
        from datetime import datetime
        until_date = datetime.fromisoformat(subscription_until)
        if until_date > datetime.now():
            days_left = (until_date - datetime.now()).days
            status_text = f"💰 **Подписка активна**\n📅 Действует до: {until_date.strftime('%d.%m.%Y')} ({days_left} дн.)"
            queries_left = "∞"
        else:
            status_text = "⚠️ **Подписка истекла**\n🔓 Используйте бесплатные запросы"
            queries_left = free_total - free_used
    elif custom_quota:
        remaining = custom_quota - free_used
        status_text = f"⭐ **Специальный доступ**\n📊 Лимит: {custom_quota} запросов"
        queries_left = remaining
    else:
        status_text = "🆓 **Бесплатный режим**"
        queries_left = free_total - free_used
    
    text = (
        f"📊 **Ваш статус**\n\n"
        f"{status_text}\n\n"
        f"📈 **Статистика:**\n"
        f"• Бесплатные запросы: {free_used}/{free_total}\n"
        f"• Осталось запросов: {queries_left}\n"
        f"• Всего анализов: {total_queries}\n\n"
    )
    
    if queries_left == 0 and not is_admin and not subscription_active:
        text += (
            f"⚠️ **У вас закончились запросы!**\n\n"
            f"💎 Оформите подписку, чтобы продолжить:\n"
            f"• 30 дней безлимита — 790 ₽\n"
            f"• 90 дней безлимита — 1990 ₽\n"
            f"• 365 дней безлимита — 5990 ₽\n\n"
            f"Отправьте /subscribe для оплаты"
        )
    
    await update.message.reply_text(text, parse_mode='Markdown')


async def _get_queries_left(user_id: int) -> int:
    """Получить количество оставшихся запросов"""
    user_data = db.get_user(user_id)
    if not user_data:
        return 3
    
    if user_data.get('is_admin') or user_data.get('subscription_active'):
        return "∞"
    
    custom_quota = user_data.get('custom_quota')
    free_used = user_data.get('free_queries_used', 0)
    
    if custom_quota:
        return custom_quota - free_used
    else:
        free_total = user_data.get('free_queries_total', 3)
        return free_total - free_used