from datetime import date

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

WEEK = "🗓 Haftalik jadval"
RESOURCES = "📚 Fan resurslari"
ATTENDANCE = "📊 Davomat"
PROFILE = "👤 Profil"
NOTIFY = "🔔 Eslatmalar"

REMIND_OPTIONS = (5, 10, 15, 30)

main = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text=WEEK), KeyboardButton(text=RESOURCES)],
        [KeyboardButton(text=ATTENDANCE), KeyboardButton(text=PROFILE)],
        [KeyboardButton(text=NOTIFY)],
    ],
    resize_keyboard=True,
)


def hemis_link(url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌐 HEMIS'da yuklash", url=url)],
    ])


def week_nav(monday: date, has_prev: bool, has_next: bool, is_current: bool) -> InlineKeyboardMarkup:
    row = []
    if has_prev:
        row.append(InlineKeyboardButton(text="◀️ Oldingi", callback_data=f"week:{monday.toordinal() - 7}"))
    if not is_current:
        row.append(InlineKeyboardButton(text="Joriy hafta", callback_data="week:now"))
    if has_next:
        row.append(InlineKeyboardButton(text="Keyingi ▶️", callback_data=f"week:{monday.toordinal() + 7}"))
    return InlineKeyboardMarkup(inline_keyboard=[row] if row else [])


def notify_settings(enabled: bool, minutes: int) -> InlineKeyboardMarkup:
    if not enabled:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔔 Yoqish", callback_data="notify:on")],
        ])
    options = [
        InlineKeyboardButton(text=f"✅ {m} daq" if m == minutes else f"{m} daq", callback_data=f"remind:{m}")
        for m in REMIND_OPTIONS
    ]
    return InlineKeyboardMarkup(inline_keyboard=[
        options,
        [InlineKeyboardButton(text="🔕 O'chirish", callback_data="notify:off")],
    ])
