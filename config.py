import os
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv()


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f".env faylida {name} ko'rsatilmagan")
    return value


BOT_TOKEN = _required("BOT_TOKEN")
HEMIS_URL = _required("HEMIS_URL").rstrip("/")
SECRET_KEY = _required("SECRET_KEY")

REMIND_BEFORE = int(os.getenv("REMIND_BEFORE", "5"))
MORNING_TIME = os.getenv("MORNING_TIME", "07:30")
TZ = ZoneInfo(os.getenv("TIMEZONE", "Asia/Tashkent"))

DB_PATH = os.getenv("DB_PATH", "bot.db")
