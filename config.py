import os

# ==== Асосӣ (Railway Variables-ро дар инҷо танзим кунед) ====

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

# Якчанд admin: дар Railway чунин нависед ADMIN_IDS=123456789,987654321
_admin_raw = os.environ.get("ADMIN_IDS", "")
ADMIN_IDS = set()
for _part in _admin_raw.split(","):
    _part = _part.strip()
    if _part.isdigit():
        ADMIN_IDS.add(int(_part))

# Рақами пардохт (метавонед аз Railway Variables иваз кунед)
PAYMENT_NUMBER = os.environ.get("PAYMENT_NUMBER", "989091111")

# Юзернейми admin барои тамос
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "@Tajwaycargo")

# Нархи пешфарз барои 1 кг (сомонӣ)
DEFAULT_PRICE_PER_KG = os.environ.get("PRICE_PER_KG", "25")

# Танзимоти пешфарзи трек
DEFAULT_ARRIVAL_CITY = os.environ.get("DEFAULT_ARRIVAL_CITY", "Истаравшан")
DEFAULT_ESTIMATED_DAYS = os.environ.get("DEFAULT_ESTIMATED_DAYS", "20-25 рӯз")

# Баъд аз чанд рӯз статус ба таври худкор ба "Дар роҳ" иваз шавад
AUTO_STATUS_DAYS = int(os.environ.get("AUTO_STATUS_DAYS", "10"))

DB_PATH = os.environ.get("DB_PATH", "cargo_bot.db")

API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"
