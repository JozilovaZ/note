import os
from typing import NamedTuple
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv()


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f".env faylida {name} ko'rsatilmagan")
    return value


BOT_TOKEN = _required("BOT_TOKEN")
SECRET_KEY = _required("SECRET_KEY")


class University(NamedTuple):
    short: str
    name: str
    url: str  # HEMIS talaba portali, oxirida / siz


# start bosilganda shu ro'yxatdan tanlanadi; yangi universitet qo'shish uchun shu yerga yozing
UNIVERSITIES = {
    "samdu": University("SamDU", "Samarqand davlat universiteti", "https://student.samdu.uz"),
    "samsi": University("SamSI", "Samarqand iqtisodiyot va servis instituti", "https://student.sies.uz"),
}
# universitet tanlash qo'shilishidan oldin kirgan foydalanuvchilar uchun
DEFAULT_UNIVERSITY = "samdu"

REMIND_BEFORE = int(os.getenv("REMIND_BEFORE", "5"))
MORNING_TIME = os.getenv("MORNING_TIME", "07:30")
# semestr davomida ruxsat etilgan sababsiz NB (soat), shunga yaqinlashganda ogohlantiriladi
ABSENCE_LIMIT = int(os.getenv("ABSENCE_LIMIT", "74"))
TZ = ZoneInfo(os.getenv("TIMEZONE", "Asia/Tashkent"))

DB_PATH = os.getenv("DB_PATH", "bot.db")
