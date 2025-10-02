# config.py
import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("API_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")  # обязательно: полный DSN
ADMIN_ID = int(os.getenv("ADMIN_ID")) if os.getenv("ADMIN_ID") else None
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "lxsonen").lstrip("@")
PORT = int(os.getenv("PORT", "8080"))

# бизнес-правила
MIN_AGE = 16
MAX_AGE = 30
DESC_LIMIT = 1200
SUPERLIKE_COOLDOWN = 24 * 3600  # сек
REFERRAL_BONUS_DAYS = 2
INACTIVE_DAYS = 30

# поведение
BACKUP_INTERVAL_MIN = 60        # бэкап в БД каждые N минут
LAST_ACTIVE_UPDATE_MIN = 5     # обновлять last_active не при каждом сообщении, а не чаще N минут
TTL_CACHE_SECONDS = 300        # кеш на выборку профилей
RATE_LIMIT_WINDOW = 10         # секунды
RATE_LIMIT_MAX = 6             # макс сообщений в окне
