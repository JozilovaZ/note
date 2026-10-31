"""Admin uchun bot statistikasi (/stats) va foydalanuvchi faolligini yozib borish."""
from html import escape
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message, TelegramObject

from config import ADMIN_IDS, UNIVERSITIES
from db import database as db
from services.scheduler import now

router = Router()
router.message.filter(F.from_user.id.in_(ADMIN_IDS))
router.callback_query.filter(F.from_user.id.in_(ADMIN_IDS))

REFRESH = "stats:refresh"
refresh_kb = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="🔄 Yangilash", callback_data=REFRESH)],
])


class ActivityMiddleware(BaseMiddleware):
    """Har bir foydalanuvchi uchun kuniga bir marta last_seen yoziladi (bazaga ortiqcha yozmaslik uchun)."""

    def __init__(self) -> None:
        self._seen: set[int] = set()
        self._day = None

    async def __call__(self, handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
                       event: TelegramObject, data: dict[str, Any]) -> Any:
        user = data.get("event_from_user")
        if user:
            today = now().date()
            if today != self._day:
                self._day, self._seen = today, set()
            if user.id not in self._seen:
                self._seen.add(user.id)
                await db.touch(user.id)
        return await handler(event, data)


def _pct(part: int, total: int) -> str:
    return f"{part * 100 // total}%" if total else "—"


def _uni_name(code: str) -> str:
    u = UNIVERSITIES.get(code)
    return u.short if u else code


def render(s: dict) -> str:
    total = s["total"]
    new, seen = s["new"], s["seen"]
    lines = [
        f"📊 <b>Bot statistikasi</b> · {now():%d.%m.%Y %H:%M}",
        "",
        f"👥 Foydalanuvchilar: <b>{total}</b>",
        f"   ✅ HEMIS'ga ulangan: {s['active_session']} ({_pct(s['active_session'], total)})",
        f"   ⚠️ Sessiyasi tugagan: {total - s['active_session']}",
        f"   🔔 Eslatmalar yoqilgan: {s['notify_on']}",
        f"   🚫 Botni bloklagan: {s['blocked']}",
        "",
        f"🆕 Yangi: bugun <b>{new[1]}</b> · 7 kun {new[7]} · 30 kun {new[30]}",
        f"🔥 Faol: bugun <b>{seen[1]}</b> · 7 kun {seen[7]} · 30 kun {seen[30]}",
        "",
        "🏛 <b>Universitetlar</b> (jami · ulangan · 7 kunda faol · 7 kunda yangi)",
    ]
    for u in s["universities"]:
        lines.append(f"   {escape(_uni_name(u['university']))}: <b>{u['total']}</b> · {u['active'] or 0}"
                     f" · {u['seen_week'] or 0} · +{u['new_week'] or 0}")
    if not s["universities"]:
        lines.append("   hali hech kim yo'q")

    lines += ["", "🔐 <b>Kirish urinishlari</b> (bugun · 7 kun)"]
    labels = (("login_ok", "✅ Muvaffaqiyatli"), ("login_fail", "❌ Login/parol xato"),
              ("login_captcha", "⏳ Captcha (429)"), ("login_error", "⚠️ HEMIS ishlamadi"),
              ("logout", "🗑 /chiqish"))
    day, week = s["logins"][1], s["logins"][7]
    for kind, label in labels:
        lines.append(f"   {label}: {day.get(kind, 0)} · {week.get(kind, 0)}")
    attempts = sum(week.get(k, 0) for k in ("login_ok", "login_fail", "login_captcha"))
    if attempts:
        lines.append(f"   Muvaffaqiyat (7 kun): <b>{_pct(week.get('login_ok', 0), attempts)}</b>")
    if s["captcha_by_uni"]:
        worst = ", ".join(f"{escape(_uni_name(u))} {n}" for u, n in s["captcha_by_uni"])
        lines.append(f"   Captcha universitetlar bo'yicha: {worst}")

    lines += ["", "<i>Yangi va faol foydalanuvchilar statistika qo'shilgan kundan boshlab hisoblanadi.</i>"]
    return "\n".join(lines)


@router.message(Command("stats"))
async def stats(message: Message):
    await message.answer(render(await db.stats(now().date())), reply_markup=refresh_kb)


@router.callback_query(F.data == REFRESH)
async def refresh(callback: CallbackQuery):
    try:
        await callback.message.edit_text(render(await db.stats(now().date())), reply_markup=refresh_kb)
    except TelegramBadRequest:  # o'zgarmagan bo'lsa ("message is not modified")
        pass
    await callback.answer("Yangilandi")
