from datetime import date, timedelta

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from config import UNIVERSITIES

WEEK = "🗓 Haftalik jadval"
RESOURCES = "📚 Fan resurslari"
ATTENDANCE = "📊 Davomat"
PROFILE = "👤 Profil"
NOTIFY = "🔔 Eslatmalar"
GPA = "📈 GPA"

REMIND_OPTIONS = (5, 10, 15, 30)

main = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text=WEEK), KeyboardButton(text=RESOURCES)],
        [KeyboardButton(text=ATTENDANCE), KeyboardButton(text=PROFILE)],
        [KeyboardButton(text=GPA), KeyboardButton(text=NOTIFY)],
    ],
    resize_keyboard=True,
)


def universities() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🏛 {u.short} — {u.name}", callback_data=f"uni:{code}")]
        for code, u in UNIVERSITIES.items()
    ])


ONEID = "oneid"

no_password = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="🆔 Parolim yo'q, OneID bilan kiraman", callback_data=ONEID)],
])


CHANGE_LOGIN = "change_login"

wrong_password = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="✏️ Loginni o'zgartirish", callback_data=CHANGE_LOGIN)],
    [InlineKeyboardButton(text="🆔 Parolim yo'q, OneID bilan kiraman", callback_data=ONEID)],
])


def oneid_help(hemis_url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌐 HEMIS'ni ochish", url=f"{hemis_url}/dashboard/login")],
    ])


def subjects(tasks: list, current, selected: int | None, hemis_url: str) -> InlineKeyboardMarkup:
    """Topshirig'i bor fanlar: avval topshirilmaganlari (eng yaqin muddat bo'yicha)."""
    by_subject: dict[int, list] = {}
    for t in tasks:
        by_subject.setdefault(t.subject_id, []).append(t)

    def pending(items):
        return [t for t in items if not t.submitted and t.deadline > current]

    order = sorted(by_subject.items(), key=lambda kv: (
        not pending(kv[1]), min((t.deadline for t in pending(kv[1])), default=current), kv[1][0].subject))
    rows = []
    for subject_id, items in order:
        name = items[0].subject
        name = name if len(name) <= 30 else name[:29].rstrip() + "…"
        count = len(pending(items))
        mark = "📖" if subject_id == selected else "📘" if count else "✅"
        label = f"{mark} {name} · {count}" if count else f"{mark} {name}"
        rows.append([InlineKeyboardButton(text=label, callback_data=f"subj:{subject_id}")])
    rows.append([
        InlineKeyboardButton(text="🔄 Yangilash", callback_data="subj:refresh"),
        InlineKeyboardButton(text="🌐 HEMIS'da yuklash", url=hemis_url),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


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
