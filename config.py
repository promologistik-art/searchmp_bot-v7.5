# config.py
import os
import logging
from dotenv import load_dotenv

load_dotenv()

# === ТОКЕНЫ ===
BOT_TOKEN = os.getenv('BOT_TOKEN')
MPSTATS_TOKEN = os.getenv('MPSTATS_TOKEN')

if not BOT_TOKEN or not MPSTATS_TOKEN:
    raise ValueError("❌ Проверьте переменные окружения: BOT_TOKEN и MPSTATS_TOKEN")

# === АДМИНЫ ===
ADMIN_IDS = []
admin_ids_str = os.getenv('ADMIN_IDS', '')
for id_str in admin_ids_str.split(','):
    id_str = id_str.strip()
    if id_str and id_str.isdigit():
        ADMIN_IDS.append(int(id_str))

ADMIN_USERNAMES = [username.strip().replace('@', '') 
                   for username in os.getenv('ADMIN_USERNAMES', '').split(',') 
                   if username.strip()]

# === ПУТЬ К ОБЩЕМУ ХРАНИЛИЩУ (bothost.ru) ===
SHARED_DIR = os.getenv('SHARED_DIR', '/app/shared')

# Пути к файлам (папки создадутся при первом обращении)
DB_DIR = os.path.join(SHARED_DIR, 'database')
DATABASE_PATH = os.path.join(DB_DIR, 'users.db')

# === ФАЙЛЫ ДЛЯ КЭШИРОВАНИЯ (в shared) ===
CACHE_DIR = os.path.join(SHARED_DIR, 'cache')
CATEGORIES_FILE = os.path.join(CACHE_DIR, 'ozon_categories.pkl')
USER_CATEGORIES_FILE = os.path.join(CACHE_DIR, 'user_categories.pkl')
HISTORY_FILE = os.path.join(CACHE_DIR, 'viewed_categories.pkl')

# === ФАЙЛЫ ДЛЯ JSON (для совместимости, могут быть в корне) ===
USERS_DB_FILE = "users_database.json"

# === ПЕРЕКЛЮЧАТЕЛЬ БАЗЫ ДАННЫХ ===
USE_SQLITE = os.getenv('USE_SQLITE', 'true').lower() == 'true'

# === API НАСТРОЙКИ ===
MPSTATS_API_URL = "https://mpstats.io/api"
HEADERS = {
    "X-Mpstats-TOKEN": MPSTATS_TOKEN,
    "Content-Type": "application/json"
}

# === СОСТОЯНИЯ ДЛЯ ДИАЛОГОВ ===
CRITERIA_CHOICE, CRITERIA_REVENUE, CRITERIA_PRICE, CRITERIA_COMPETITORS, CRITERIA_VOLUME = range(5)
UPLOAD_CATEGORIES = 5

# === СПИСКИ ИСКЛЮЧЕНИЙ ===
EXCLUDED = [
    "туалетная бумага", "туалетная", "бумага туалетная", "туалетные",
    "одежда", "ткани", "постельное", "белье", "платье", "юбка", "брюки",
    "джинсы", "футболка", "рубашка", "кофта", "свитер", "куртка", "пальто",
    "пуховик", "костюм", "пиджак", "жилет", "шорты", "топ", "блуза",
    "туника", "комбинезон", "пижама", "халат", "носки", "колготки",
    "перчатки", "варежки", "шапка", "шарф", "кепка", "бейсболка",
    "продукты", "еда", "питание", "продуктовый", "гастроном",
    "напитки", "вода", "сок", "газировка", "лимонад", "квас", "чай", "кофе",
    "молоко", "кефир", "йогурт", "ряженка", "творог", "сыр",
    "масло", "сметана", "сливки", "маргарин",
    "мясо", "курица", "индейка", "рыба", "морепродукты",
    "колбаса", "сосиски", "пельмени", "вареники", "котлеты",
    "овощи", "фрукты", "ягоды", "грибы", "зелень",
    "консервы", "тушенка", "крупы", "гречка", "рис", "макароны",
    "мука", "сахар", "соль", "специи", "майонез", "кетчуп", "соус",
    "шоколад", "конфеты", "печенье", "пряники", "вафли", "зефир",
    "хлеб", "булка", "батон", "лаваш", "торт", "пирожное", "выпечка",
    "завтрак", "обед", "ужин", "перекус", "снеки", "чипсы", "сухарики",
    "орехи", "семечки", "сухофрукты", "батончик", "мюсли",
    "готовая еда", "кулинария", "полуфабрикаты", "заморозка",
    "пицца", "бургер", "хот-дог", "шаурма", "суши", "роллы",
    "азбука вкуса", "ozon fresh", "вкусвилл",
    "бакалея", "гастрономия", "консервация",
    "лекарство", "таблетки", "витамины", "бады", "аптека", "гомеопатия",
]

LARGE_CATEGORIES = [
    "мебель", "шкаф", "стол", "стул", "кровать", "диван", "кресло",
    "холодильник", "стиральная", "машина", "пылесос", "телевизор",
    "велосипед", "самокат", "лыжи", "сноуборд", "ковер", "палас",
    "стройматериалы", "доска", "брус", "гипсокартон", "цемент",
]

CATCOM_PATH = "catcom.xlsx"

# === НАСТРОЙКА ЛОГИРОВАНИЯ ===
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

print(f"✅ Config loaded. USE_SQLITE={USE_SQLITE}, SHARED_DIR={SHARED_DIR}")
print(f"✅ ADMIN_IDS: {ADMIN_IDS}")
print(f"✅ ADMIN_USERNAMES: {ADMIN_USERNAMES}")