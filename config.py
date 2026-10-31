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
# /stats buyrug'idan foydalana oladigan Telegram ID'lar, vergul bilan: ADMIN_IDS=123,456
ADMIN_IDS = frozenset(int(x) for x in os.getenv("ADMIN_IDS", "").replace(" ", "").split(",") if x.isdigit())


class University(NamedTuple):
    short: str
    name: str
    url: str  # HEMIS talaba portali, oxirida / siz


# start bosilganda shu ro'yxatdan tanlanadi; yangi universitet qo'shish uchun shu yerga yozing
UNIVERSITIES = {
    "samdu": University("SamDU", "Samarqand davlat universiteti", "https://student.samdu.uz"),
    "samsi": University("SamSI", "Samarqand iqtisodiyot va servis instituti", "https://student.sies.uz"),
    "samdtu": University("SamDTU", "Samarqand davlat tibbiyot universiteti", "https://student.sammu.uz"),
    "samdaqu": University("SamDAQU", "Samarqand davlat arxitektura-qurilish universiteti",
                          "https://student.samdaqu.edu.uz"),
    "samdchti": University("SamDChTI", "Samarqand davlat chet tillar instituti", "https://student.samdchti.uz"),
    "silkroad": University("Ipak yo'li", "\"Ipak yo'li\" turizm va madaniy meros xalqaro universiteti",
                           "https://student.univ-silkroad.uz"),
    "samdpi": University("SamDPI", "Samarqand davlat pedagogika instituti", "https://student.samdpi.uz"),
    "samvmi": University("SamDVMChBU", "Samarqand davlat veterinariya meditsinasi, chorvachilik va "
                         "biotexnologiyalar universiteti", "https://student.otmsamvmi.uz"),
    "uzfi": University("O'zFinPI", "O'zbekiston-Finlandiya pedagogika instituti", "https://student.uzfi.uz"),
    "saiti": University("SAITI", "Samarqand agroinnovatsiyalar va tadqiqotlar instituti",
                        "https://student.samaguni.uz"),
    # student.katdpi.uz shu manzilga yo'naltiradi; POST yo'naltirishda yo'qolgani uchun to'g'ridan-to'g'ri
    "kdpi": University("KDPI", "Kattaqo'rg'on davlat pedagogika instituti", "https://student.samdukf.uz"),
}
# universitet tanlash qo'shilishidan oldin kirgan foydalanuvchilar uchun
DEFAULT_UNIVERSITY = "samdu"

REMIND_BEFORE = int(os.getenv("REMIND_BEFORE", "5"))
MORNING_TIME = os.getenv("MORNING_TIME", "07:30")
# semestr davomida ruxsat etilgan sababsiz NB (soat), shunga yaqinlashganda ogohlantiriladi
ABSENCE_LIMIT = int(os.getenv("ABSENCE_LIMIT", "74"))
TZ = ZoneInfo(os.getenv("TIMEZONE", "Asia/Tashkent"))

DB_PATH = os.getenv("DB_PATH", "bot.db")
