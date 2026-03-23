# services/analysis_service.py
# -*- coding: utf-8 -*-

"""
Сервис анализа товаров на Ozon
Основная бизнес-логика поиска, фильтрации и генерации отчетов
"""

import asyncio
import logging
import io
import math
from datetime import datetime
from typing import List, Dict, Optional, Tuple

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from storage.database import db
from config import ADMIN_IDS, ADMIN_USERNAMES, logger, CATCOM_PATH
from categories import load_cached_categories, load_user_categories
from api.mpstats_api import MPStatsAPI
from excel_handler import create_excel_report
from utils.helpers import safe_get, normalize_string

logger = logging.getLogger(__name__)


async def analyze_command(update: Update, context: ContextTypes.DEFAULT_TYPE, 
                          admin_ids: list, admin_usernames: list):
    """
    Основной обработчик команды /analyze
    Проверяет лимиты, собирает данные, генерирует отчет
    """
    user = update.effective_user
    user_id = user.id
    username = user.username or "нет username"
    
    # === 1. ПРОВЕРКА ПРАВ И ЛИМИТОВ ===
    can_use, reason = db.can_use_bot(user_id)
    
    if not can_use:
        await update.message.reply_text(
            f"{reason}\n\n"
            f"💎 **Оформите подписку:** /subscribe\n"
            f"📊 **Проверить статус:** /status\n"
            f"🔧 **Настроить критерии:** /criteria",
            parse_mode='Markdown'
        )
        return
    
    # === 2. ПРОВЕРКА ВЫБРАННЫХ КАТЕГОРИЙ ===
    selected = context.user_data.get('selected', [])
    use_user_cats = context.user_data.get('use_user_cats', False)
    
    if not selected:
        # Проверяем, есть ли у пользователя сохраненные категории
        user_categories = load_user_categories(user_id)
        if user_categories:
            keyboard = [
                [InlineKeyboardButton("✅ Использовать сохраненные", callback_data="use_user_cats")],
                [InlineKeyboardButton("📋 Выбрать из списка", callback_data="goto_list")],
                [InlineKeyboardButton("📤 Загрузить новые", callback_data="upload_again")]
            ]
            await update.message.reply_text(
                "❌ У вас нет выбранных категорий для анализа.\n\n"
                f"📁 Найдены сохраненные категории ({len(user_categories)} шт.)\n\n"
                "Хотите использовать их?",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await update.message.reply_text(
                "❌ У вас нет выбранных категорий.\n\n"
                "📋 **Выберите категории:** /list\n"
                "📤 **Загрузите свои категории:** /upload\n"
                "🔧 **Настройте критерии:** /criteria",
                parse_mode='Markdown'
            )
        return
    
    # === 3. ПОЛУЧАЕМ КРИТЕРИИ АНАЛИЗА ===
    criteria = context.user_data.get('criteria', {
        'min_revenue': 1000000,
        'max_price': 1000,
        'competitors': '2-3',
        'max_volume': 2.0
    })
    
    # === 4. УВЕЛИЧИВАЕМ СЧЕТЧИК ЗАПРОСОВ ===
    db.increment_queries(user_id)
    
    # Сохраняем историю анализа
    db.add_analysis_history(user_id, len(selected), criteria)
    
    # === 5. УВЕДОМЛЯЕМ АДМИНОВ (опционально) ===
    await _notify_admin_about_analyze(update, context, user, len(selected), criteria)
    
    # === 6. ЗАПУСКАЕМ АНАЛИЗ ===
    status_msg = await update.message.reply_text(
        f"🔍 **Анализирую {len(selected)} категорий...**\n\n"
        f"📊 Критерии:\n"
        f"  • Выручка > {criteria['min_revenue']:,} руб\n"
        f"  • Цена ≤ {criteria['max_price']} руб\n"
        f"  • Конкуренты: {criteria['competitors']}\n"
        f"  • Объем ≤ {criteria['max_volume']} л\n\n"
        f"⏳ Это займет от 30 секунд до 2 минут...",
        parse_mode='Markdown'
    )
    
    try:
        # Запускаем анализ
        results = await run_analysis(selected, criteria, user_id, use_user_cats)
        
        if not results:
            await status_msg.edit_text(
                "❌ **Ничего не найдено**\n\n"
                "Попробуйте изменить критерии:\n"
                "• Уменьшить минимальную выручку\n"
                "• Увеличить максимальную цену\n"
                "• Выбрать другие категории\n\n"
                "🔧 /criteria - изменить настройки\n"
                "📋 /list - выбрать другие категории",
                parse_mode='Markdown'
            )
            return
        
        # === 7. ГЕНЕРИРУЕМ EXCEL-ОТЧЕТ ===
        await status_msg.edit_text("📊 Генерирую Excel-отчет с формулами...")
        
        excel_file = create_excel_report(results)
        
        # === 8. ФОРМИРУЕМ ТЕКСТОВОЕ СООБЩЕНИЕ ===
        total_products = len(results)
        total_revenue = sum(r.get('revenue', 0) for r in results)
        avg_price = sum(r.get('price', 0) for r in results) / total_products if total_products else 0
        
        # Получаем обновленную статистику пользователя
        user_data = db.get_user(user_id)
        free_used = user_data.get('free_queries_used', 0)
        free_total = user_data.get('free_queries_total', 3)
        custom_quota = user_data.get('custom_quota')
        
        # Определяем статус для отображения
        if user_data.get('is_admin'):
            queries_left = "∞"
            quota_text = "👑 Администратор"
        elif user_data.get('subscription_active'):
            queries_left = "∞"
            quota_text = "💰 Подписка"
        elif custom_quota:
            remaining = custom_quota - free_used
            queries_left = f"{remaining}/{custom_quota}"
            quota_text = f"⭐ Спец. доступ"
        else:
            remaining = free_total - free_used
            queries_left = remaining
            quota_text = f"🆓 Бесплатные: {free_used}/{free_total}"
        
        # Формируем сообщение с результатами
        result_text = (
            f"✅ **Анализ завершен!**\n\n"
            f"📊 **Статистика:**\n"
            f"  • Категорий: {len(selected)}\n"
            f"  • Найдено товаров: {total_products}\n"
            f"  • Суммарная выручка: {total_revenue:,.0f} руб\n"
            f"  • Средняя цена: {avg_price:.0f} руб\n\n"
            f"📈 **Ваш статус:**\n"
            f"  • {quota_text}\n"
            f"  • Осталось запросов: {queries_left}\n\n"
            f"📁 **Файл с результатами готов!**\n\n"
            f"💡 *В файле есть формулы для расчета маржи и ROI*\n"
            f"🔧 *Изменить критерии:* /criteria\n"
            f"📋 *Другие категории:* /list"
        )
        
        # === 9. ОТПРАВЛЯЕМ ФАЙЛ И СООБЩЕНИЕ ===
        filename = f"ozon_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        
        await status_msg.delete()
        
        await update.message.reply_document(
            document=excel_file,
            filename=filename,
            caption=result_text,
            parse_mode='Markdown'
        )
        
        # === 10. ЛОГИРУЕМ УСПЕШНЫЙ АНАЛИЗ ===
        logger.info(f"✅ Анализ завершен: user={user_id}, categories={len(selected)}, products={total_products}")
        
        # Проверяем, не подходит ли лимит к концу
        if not user_data.get('is_admin') and not user_data.get('subscription_active'):
            remaining = _get_remaining_queries(user_data)
            if remaining <= 2:
                await update.message.reply_text(
                    "⚠️ **Внимание!**\n\n"
                    f"У вас осталось всего {remaining} бесплатных запросов.\n\n"
                    "💰 Оформите подписку, чтобы продолжить пользоваться ботом:\n"
                    "• 30 дней безлимита — 790 ₽\n"
                    "• 90 дней безлимита — 1990 ₽\n\n"
                    "Отправьте /subscribe для оформления",
                    parse_mode='Markdown'
                )
        
    except Exception as e:
        logger.error(f"Ошибка при анализе для пользователя {user_id}: {e}", exc_info=True)
        await status_msg.edit_text(
            f"❌ **Произошла ошибка при анализе**\n\n"
            f"`{str(e)[:200]}`\n\n"
            f"Попробуйте позже или обратитесь к администратору.\n"
            f"📊 /status - проверить статус",
            parse_mode='Markdown'
        )


async def run_analysis(selected_categories: List[Dict], criteria: Dict, 
                       user_id: int, use_user_cats: bool = False) -> List[Dict]:
    """
    Запускает анализ категорий
    Возвращает список товаров, подходящих под критерии
    """
    results = []
    api = MPStatsAPI()
    
    # Параметры из критериев
    min_revenue = criteria.get('min_revenue', 1000000)
    max_price = criteria.get('max_price', 1000)
    competitors_range = criteria.get('competitors', '2-3')
    max_volume = criteria.get('max_volume', 2.0)
    
    # Парсим диапазон конкурентов
    min_competitors, max_competitors = _parse_competitors_range(competitors_range)
    
    # Ограничиваем количество категорий для анализа (чтобы не превысить лимиты API)
    max_categories = 50
    if len(selected_categories) > max_categories:
        logger.warning(f"Слишком много категорий: {len(selected_categories)}, ограничиваю до {max_categories}")
        selected_categories = selected_categories[:max_categories]
    
    # Прогресс-бар для отслеживания (в логах)
    total_categories = len(selected_categories)
    processed = 0
    
    for cat in selected_categories:
        try:
            category_path = cat.get('path', '')
            category_name = cat.get('name', '')
            
            if not category_path:
                continue
            
            # Запрашиваем товары из категории
            products = await api.get_category_products(
                category_path=category_path,
                limit=100  # Максимум 100 товаров на категорию
            )
            
            if not products:
                continue
            
            # Фильтруем товары по критериям
            for product in products:
                if _matches_criteria(product, min_revenue, max_price, 
                                    min_competitors, max_competitors, max_volume):
                    # Добавляем информацию о категории
                    product['category'] = category_name
                    product['category_path'] = category_path
                    results.append(product)
            
            processed += 1
            if processed % 10 == 0:
                logger.info(f"Прогресс анализа: {processed}/{total_categories} категорий")
            
            # Небольшая задержка, чтобы не перегружать API
            await asyncio.sleep(0.5)
            
        except Exception as e:
            logger.error(f"Ошибка при анализе категории {cat.get('name')}: {e}")
            continue
    
    # Сортируем по выручке (от большего к меньшему)
    results.sort(key=lambda x: x.get('revenue', 0), reverse=True)
    
    # Ограничиваем количество результатов
    max_results = 500
    if len(results) > max_results:
        results = results[:max_results]
    
    return results


async def get_product_details(product_id: int) -> Optional[Dict]:
    """
    Получает детальную информацию о товаре
    """
    try:
        api = MPStatsAPI()
        return await api.get_product_details(product_id)
    except Exception as e:
        logger.error(f"Ошибка получения деталей товара {product_id}: {e}")
        return None


def _matches_criteria(product: Dict, min_revenue: int, max_price: int,
                      min_competitors: int, max_competitors: int, max_volume: float) -> bool:
    """
    Проверяет, соответствует ли товар критериям
    """
    # Проверяем выручку
    revenue = product.get('revenue', 0)
    if revenue < min_revenue:
        return False
    
    # Проверяем цену
    price = product.get('price', 0)
    if price > max_price:
        return False
    
    # Проверяем количество конкурентов
    competitors = product.get('competitors_count', 0)
    if competitors < min_competitors or competitors > max_competitors:
        return False
    
    # Проверяем объем (если есть данные)
    volume = product.get('volume', 0)
    if volume > max_volume:
        return False
    
    return True


def _parse_competitors_range(comp_str: str) -> Tuple[int, int]:
    """
    Парсит строку с диапазоном конкурентов
    Возвращает (min, max)
    """
    if comp_str == 'any':
        return 0, 999999
    
    if '-' in comp_str:
        parts = comp_str.split('-')
        try:
            return int(parts[0]), int(parts[1])
        except:
            return 0, 999999
    
    try:
        val = int(comp_str)
        return val, val
    except:
        return 0, 999999


def _get_remaining_queries(user_data: Dict) -> int:
    """
    Получает количество оставшихся запросов
    """
    if user_data.get('is_admin') or user_data.get('subscription_active'):
        return 999999
    
    custom_quota = user_data.get('custom_quota')
    free_used = user_data.get('free_queries_used', 0)
    
    if custom_quota:
        return custom_quota - free_used
    else:
        free_total = user_data.get('free_queries_total', 3)
        return free_total - free_used


async def _notify_admin_about_analyze(update: Update, context: ContextTypes.DEFAULT_TYPE,
                                       user, categories_count: int, criteria: Dict):
    """
    Уведомляет админов о запуске анализа
    """
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
        f"📈 Критерии: выручка > {criteria.get('min_revenue', 0):,}, цена ≤ {criteria.get('max_price', 0)}\n"
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


async def check_quota_and_warn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Проверяет квоту пользователя и предупреждает, если она заканчивается
    Вызывается после каждого анализа
    """
    user = update.effective_user
    user_data = db.get_user(user.id)
    
    if not user_data:
        return
    
    if user_data.get('is_admin') or user_data.get('subscription_active'):
        return
    
    remaining = _get_remaining_queries(user_data)
    
    # Предупреждаем, если осталось 1 или 2 запроса
    if remaining == 1:
        await update.message.reply_text(
            "⚠️ **Внимание!**\n\n"
            "У вас остался **1 бесплатный запрос**.\n\n"
            "💰 Оформите подписку, чтобы продолжить:\n"
            "• 30 дней безлимита — 790 ₽\n"
            "• 90 дней безлимита — 1990 ₽\n\n"
            "Отправьте /subscribe для оформления",
            parse_mode='Markdown'
        )
    elif remaining == 2:
        await update.message.reply_text(
            "⚠️ **Осталось 2 бесплатных запроса**\n\n"
            "После этого вам нужно будет оформить подписку.\n"
            "💰 /subscribe - посмотреть тарифы",
            parse_mode='Markdown'
        )


async def get_analysis_stats(user_id: int) -> Dict:
    """
    Получает статистику анализов пользователя
    """
    user_data = db.get_user(user_id)
    if not user_data:
        return {}
    
    return {
        'total_queries': user_data.get('total_queries', 0),
        'free_used': user_data.get('free_queries_used', 0),
        'free_total': user_data.get('free_queries_total', 3),
        'custom_quota': user_data.get('custom_quota'),
        'subscription_active': user_data.get('subscription_active', False),
        'is_admin': user_data.get('is_admin', False)
    }


# === ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ДЛЯ РАБОТЫ С КОМИССИЯМИ ===

async def calculate_commission(category_id: int, price: float) -> float:
    """
    Рассчитывает комиссию Ozon для товара
    """
    try:
        import pandas as pd
        if not CATCOM_PATH or not pd.io.common.file_exists(CATCOM_PATH):
            logger.warning("Файл с комиссиями не найден")
            return 0.1 * price  # Комиссия 10% по умолчанию
        
        df = pd.read_excel(CATCOM_PATH)
        # Поиск комиссии по категории
        # Логика зависит от структуры файла comcat.xlsx
        # Здесь нужно адаптировать под ваш файл
        
        return price * 0.1  # Временное значение
        
    except Exception as e:
        logger.error(f"Ошибка расчета комиссии: {e}")
        return price * 0.1


async def calculate_logistics(price: float, weight: float, volume: float) -> float:
    """
    Рассчитывает стоимость логистики
    """
    # Базовая логика для FBO
    if weight <= 0.5:
        return 50
    elif weight <= 1:
        return 70
    elif weight <= 2:
        return 100
    elif weight <= 5:
        return 150
    else:
        return 200


async def calculate_acquiring(price: float) -> float:
    """
    Рассчитывает эквайринг (1.5-3% от цены)
    """
    return price * 0.02  # 2% по умолчанию


# === ФУНКЦИИ ДЛЯ РАБОТЫ С КЭШЕМ (опционально) ===

class AnalysisCache:
    """
    Простой in-memory кэш для результатов анализа
    """
    def __init__(self, ttl_seconds: int = 21600):  # 6 часов по умолчанию
        self.cache = {}
        self.ttl = ttl_seconds
    
    def _get_key(self, categories_hash: str, criteria_hash: str) -> str:
        return f"{categories_hash}:{criteria_hash}"
    
    def get(self, categories_hash: str, criteria_hash: str) -> Optional[List[Dict]]:
        key = self._get_key(categories_hash, criteria_hash)
        if key in self.cache:
            data, timestamp = self.cache[key]
            if datetime.now().timestamp() - timestamp < self.ttl:
                return data
            del self.cache[key]
        return None
    
    def set(self, categories_hash: str, criteria_hash: str, data: List[Dict]):
        key = self._get_key(categories_hash, criteria_hash)
        self.cache[key] = (data, datetime.now().timestamp())
    
    def clear(self):
        self.cache.clear()


# Создаем глобальный экземпляр кэша (опционально)
analysis_cache = AnalysisCache()