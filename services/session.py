"""HEMIS sessiyasi: token tugaganda saqlangan parol bilan avtomatik qayta kirish."""
import asyncio
import logging
from datetime import datetime, timedelta

from config import TZ
from db import database as db
from hemis import client as hemis

log = logging.getLogger(__name__)

RATE_LIMIT_PAUSE = timedelta(minutes=5)
# universitet -> HEMIS'ga qayta kirishga urinish mumkin bo'lgan vaqt (429 captcha'dan keyin)
rate_limited_until: dict[str, datetime] = {}
_locks: dict[int, asyncio.Lock] = {}


def _now() -> datetime:
    return datetime.now(TZ)


def rate_limited(university: str) -> datetime | None:
    until = rate_limited_until.get(university)
    return until if until and _now() < until else None


def set_rate_limited(university: str) -> datetime:
    until = rate_limited_until[university] = _now() + RATE_LIMIT_PAUSE
    return until


async def relogin(telegram_id: int, expired_token: str | None) -> hemis.Auth:
    """Saqlangan parol bilan yangi token oladi.

    Parol yo'q yoki HEMIS uni qabul qilmasa -> TokenExpired (talaba /start bosishi kerak).
    HEMIS vaqtincha ishlamasa -> HemisError (token o'chirilmaydi, keyingi safar yana urinadi).
    """
    lock = _locks.setdefault(telegram_id, asyncio.Lock())
    async with lock:
        user = await db.get_user(telegram_id)
        if not user:
            raise hemis.TokenExpired()
        auth = db.auth(user)
        if auth and auth.token != expired_token:
            return auth  # boshqa so'rov allaqachon qayta kirib bo'lgan
        password = db.decrypt_token(user["password"])
        if not password:
            raise hemis.TokenExpired()
        uni = user["university"]
        if until := rate_limited(uni):
            raise hemis.HemisError(f"HEMIS {until:%H:%M} gacha captcha talab qilyapti")
        url = db.university(user).url
        try:
            token = await hemis.login(url, user["hemis_login"], password)
        except hemis.RateLimited:
            await db.count("login_captcha", uni)
            set_rate_limited(uni)
            raise
        except (hemis.LoginError, hemis.ApiError) as e:
            # parol o'zgargan yoki HEMIS rad etdi: qayta-qayta urinib captcha chaqirmaslik uchun
            # parolni unutamiz, talaba bir marta /start orqali kiradi
            log.info("Avtomatik qayta kirish bo'lmadi (%s): %r", telegram_id, e)
            await db.count("relogin_fail", uni)
            await db.forget_password(telegram_id)
            raise hemis.TokenExpired() from e
        await db.set_token(telegram_id, token)
        await db.count("relogin_ok", uni)
        log.info("Avtomatik qayta kirildi: %s", telegram_id)
        return hemis.Auth(url, token)


async def call(telegram_id: int, fetch):
    """fetch(auth) ni bajaradi; token tugagan bo'lsa jim qayta kirib, yana bir marta urinadi.

    Qayta kirib bo'lmasa TokenExpired chiqadi (shunda chaqiruvchi tokenni o'chirib, xabar beradi).
    """
    user = await db.get_user(telegram_id)
    auth = db.auth(user)
    if not auth:
        raise hemis.TokenExpired()
    try:
        return await fetch(auth)
    except hemis.TokenExpired:
        auth = await relogin(telegram_id, auth.token)
    return await fetch(auth)
