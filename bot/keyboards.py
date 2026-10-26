from datetime import date, timedelta

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


DAY_NAMES = ["Dushanba", "Seshanba", "Chorshanba", "Payshanba", "Juma", "Shanba", "Yakshanba"]


def week_days(monday: date, counts: dict[date, int], today: date, selected: date | None,
              has_prev: bool, has_next: bool, is_current: bool) -> InlineKeyboardMarkup:
    """Hafta kunlari tugmalari (Du–Sha, yakshanba faqat darsi bo'lsa) va hafta almashtirish."""
    buttons = []
    for i in range(7):
        day = monday + timedelta(days=i)
        if i == 6 and not counts.get(day):
            continue
        mark = "✅ " if day == selected else "👉 " if day == today else ""
        count = counts.get(day, 0)
        label = f"{mark}{DAY_NAMES[i]} · {count}" if count else f"{mark}{DAY_NAMES[i]} · —"
        buttons.append(InlineKeyboardButton(text=label, callback_data=f"day:{day.toordinal()}"))
    rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]

    nav = []
    if has_prev:
        nav.append(InlineKeyboardButton(text="◀️ Oldingi", callback_data=f"week:{monday.toordinal() - 7}"))
    if not is_current:
        nav.append(InlineKeyboardButton(text="Joriy hafta", callback_data="week:now"))
    if has_next:
        nav.append(InlineKeyboardButton(text="Keyingi ▶️", callback_data=f"week:{monday.toordinal() + 7}"))
    if nav:
        rows.append(nav)
    return InlineKeyboardMarkup(inline_keyboard=rows)


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
