# config.py
import os
from dotenv import load_dotenv

load_dotenv()

# Токен бота
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("API_TOKEN")

# Supabase (Session Pooler URL)
DATABASE_URL = os.getenv("DATABASE_URL")  # обязательно: postgresql://...:6543/...

# Админка
ADMIN_ID = int(os.getenv("ADMIN_ID")) if os.getenv("ADMIN_ID") else None
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "lxsonen").lstrip("@")

# Порт (для локального запуска или keepalive)
PORT = int(os.getenv("PORT", "8080"))

# 🔥 НОВОЕ: URL вебхука для Telegram
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # Например: https://your-project.vercel.app/api/webhook

# Бизнес-правила
MIN_AGE = 16
MAX_AGE = 30
DESC_LIMIT = 1200
SUPERLIKE_COOLDOWN = 24 * 3600  # сек
REFERRAL_BONUS_DAYS = 2
INACTIVE_DAYS = 30

# Поведение
BACKUP_INTERVAL_MIN = 60        # ⚠️ На Vercel бэкапы нужно делать через cron (GitHub Actions)
LAST_ACTIVE_UPDATE_MIN = 5
TTL_CACHE_SECONDS = 300
RATE_LIMIT_WINDOW = 10
RATE_LIMIT_MAX = 6
