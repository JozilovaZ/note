"""Xabar matnlari. Jadval va davomat HEMIS Student sahifalari uslubida."""
from datetime import date, datetime, timedelta
from html import escape

from hemis.client import Absence, Lesson, Task

WEEKDAYS = ["Dushanba", "Seshanba", "Chorshanba", "Payshanba", "Juma", "Shanba", "Yakshanba"]
MONTHS = ["yanvar", "fevral", "mart", "aprel", "may", "iyun",
          "iyul", "avgust", "sentabr", "oktabr", "noyabr", "dekabr"]


def _e(text: str) -> str:
    return escape(text, quote=False)


def long_date(day: date) -> str:
    """14 oktabr, 2026"""
    return f"{day.day} {MONTHS[day.month - 1]}, {day.year}"


def _short_date(day: date) -> str:
    """14 oktabr"""
    return f"{day.day} {MONTHS[day.month - 1]}"


def lesson_line(lesson: Lesson) -> str:
    """1. Elektron hukumat
    Telek_308 / Ma'ruza / SHODMONOV D. A.  ·  09:00"""
    details = " / ".join(
        x for x in (f"<b>{_e(lesson.room)}</b>" if lesson.room else "",
                    _e(lesson.kind), _e(lesson.teacher)) if x
    )
    return f"<b>{_e(lesson.pair)}. {_e(lesson.subject)}</b>\n{details}  ·  <b>{lesson.start}</b>"


def _day_title(day: date, today: date | None = None) -> str:
    """📅 SHANBA  ·  31.10"""
    mark = "  —  <i>bugun</i>" if day == today else ""
    return f"📅 <b>{WEEKDAYS[day.weekday()].upper()}  ·  {day:%d.%m}</b>{mark}"


def _day_card(day: date, lessons: list[Lesson], today: date | None = None) -> str:
    body = "\n\n".join(lesson_line(l) for l in lessons)
    return f"{_day_title(day, today)}\n<blockquote>{body}</blockquote>"


def day_schedule(day: date, lessons: list[Lesson]) -> str:
    if not lessons:
        return f"{_day_title(day)}\n\nBu kuni dars yo'q 🎉"
    return _day_card(day, lessons)


def week_schedule(monday: date, lessons: list[Lesson], today: date, group: str = "",
                  selected: date | None = None) -> str:
    """Hafta sarlavhasi; kun tanlangan bo'lsa — o'sha kunning darslari."""
    sunday = monday + timedelta(days=6)
    header = "🗓 <b>Dars jadvali</b>" + (f"  ·  {_e(group)}" if group else "")
    week = f"<b>{_short_date(monday)} / {_short_date(sunday)}</b>"
    if monday <= today <= sunday:
        week += "  ·  <i>joriy hafta</i>"
    week += f"  ·  {len(lessons)} ta dars"

    if selected is None:
        hint = "Bu hafta dars yo'q." if not lessons else "Kunni tanlang 👇"
        return f"{header}\n{week}\n\n{hint}"
    day_lessons = [l for l in lessons if l.day == selected]
    if not day_lessons:
        return f"{header}\n{week}\n\n{_day_title(selected, today)}\n<i>Bu kuni dars yo'q 🎉</i>"
    return f"{header}\n{week}\n\n{_day_card(selected, day_lessons, today)}"


def reminder(lesson: Lesson, minutes: int) -> str:
    return f"🔔 <b>{minutes} daqiqadan keyin dars!</b>\n\n<blockquote>{lesson_line(lesson)}</blockquote>"


def _absence_row(a: Absence, prefix: str = "") -> str:
    details = " / ".join(x for x in (long_date(a.day), _e(a.kind), _e(a.teacher)) if x)
    excused_text = "Ha" if a.excused else "Yo'q"
    return (
        f"<b>{prefix}{_e(a.subject)}</b>\n"
        f"{details}\n"
        f"Soatlar: <b>{a.hours}</b>  ·  Sababli: <b>{excused_text}</b>"
    )


def new_absence(a: Absence, subject_total: int, semester_total: int) -> str:
    return (
        "🚨 <b>Sizga NB qo'yildi!</b>\n\n"
        f"<blockquote>{_absence_row(a)}</blockquote>\n\n"
        f"Bu fandan jami: <b>{subject_total} soat</b>\n"
        f"Semestr bo'yicha jami: <b>{semester_total} soat</b>"
    )


def absence_excused(a: Absence) -> str:
    return f"✅ <b>NB sababli deb belgilandi</b>\n\n<blockquote>{_absence_row(a)}</blockquote>"


def attendance(absences: list[Absence], group: str = "") -> str:
    header = "📊 <b>Davomat</b>" + (f"  ·  {_e(group)}" if group else "")
    if not absences:
        return f"{header}\n\nMa'lumotlar mavjud emas — qoldirilgan dars yo'q 👏"

    unexcused = sum(a.hours for a in absences if not a.excused)
    excused = sum(a.hours for a in absences if a.excused)
    rows = [_absence_row(a, f"{i}. ") for i, a in enumerate(absences, 1)]
    return (
        f"{header}\n"
        f"Jami: <b>{unexcused + excused} soat</b>  ·  sababsiz: <b>{unexcused}</b>  ·  sababli: <b>{excused}</b>\n\n"
        "<blockquote>" + "\n\n".join(rows) + "</blockquote>"
    )


def _section(title: str, rows: list[tuple[str, str]]) -> str:
    lines = [f"{label}: <b>{_e(value)}</b>" for label, value in rows if value]
    return f"{title}\n<blockquote>" + "\n".join(lines) + "</blockquote>" if lines else ""


# ---------- Fan resurslari (topshiriqlar) ----------

def time_left(deadline: datetime, current: datetime) -> str:
    minutes = int((deadline - current).total_seconds() // 60)
    days, hours = minutes // 1440, minutes % 1440 // 60
    if days:
        return f"{days} kun {hours} soat" if hours else f"{days} kun"
    return f"{hours} soat {minutes % 60} daqiqa" if hours else f"{minutes % 60} daqiqa"


def _deadline(t: Task) -> str:
    return f"{t.deadline.day} {MONTHS[t.deadline.month - 1]}, {t.deadline:%H:%M}"


def _task_row(t: Task, current: datetime, with_subject: bool = False, prefix: str = "") -> str:
    lines = [f"<b>{_e(t.subject)}</b>"] if with_subject else []
    lines.append(f"<b>{prefix}{_e(t.name)}</b>" if not with_subject else _e(t.name))
    left = time_left(t.deadline, current)
    urgent = "🔴" if t.deadline - current <= timedelta(days=1) else "🟡" if t.deadline - current <= timedelta(days=3) else "🟢"
    lines.append("")
    lines.append(f"📅 Muddat: <b>{_deadline(t)}</b>")
    lines.append(f"{urgent} <b>{left} qoldi</b>")
    attempts = f"  ·  Urinish: {t.attempt_count}/{t.attempt_limit}" if t.attempt_limit else ""
    teacher = f"  ·  {_e(t.teacher)}" if t.teacher else ""
    lines.append(f"Ball: {t.max_ball}{attempts}{teacher}")
    for name, url in t.files:
        lines.append(f'📎 <a href="{escape(url)}">{_e(name)}</a>')
    return "\n".join(lines)


def _tasks_header(tasks: list[Task], current: datetime) -> str:
    pending = sum(1 for t in tasks if not t.submitted and t.deadline > current)
    missed = sum(1 for t in tasks if not t.submitted and t.deadline <= current)
    done = sum(1 for t in tasks if t.submitted)
    return (
        "📚 <b>Fan resurslari</b>  ·  topshiriqlar\n"
        f"⏳ Topshirilmagan: <b>{pending}</b>  ·  ✅ Topshirilgan: <b>{done}</b>"
        + (f"  ·  ❌ Muddati o'tgan: <b>{missed}</b>" if missed else "")
    )


def tasks_overview(tasks: list[Task], current: datetime) -> str:
    if not tasks:
        return "📚 <b>Fan resurslari</b>\n\nJoriy semestrda topshiriqlar yo'q."
    return f"{_tasks_header(tasks, current)}\n\nFanni tanlang 👇"


def subject_tasks(tasks: list[Task], subject_id: int, current: datetime) -> str:
    """Tanlangan fan: topshirilmaganlar to'liq, qolganlari qisqa ro'yxat."""
    items = [t for t in tasks if t.subject_id == subject_id]
    header = _tasks_header(tasks, current)
    if not items:
        return f"{header}\n\nBu fan bo'yicha topshiriq topilmadi."

    pending = [t for t in items if not t.submitted and t.deadline > current]
    done = [t for t in items if t.submitted]
    missed = [t for t in items if not t.submitted and t.deadline <= current]
    parts = [header, f"📘 <b>{_e(items[0].subject.upper())}</b>"]
    if pending:
        rows = []
        for i, t in enumerate(pending, 1):
            row = _task_row(t, current, prefix=f"{i}. ")
            if sum(len(r) for r in rows) + len(row) > 3000:  # Telegram chegarasi 4096
                rows.append(f"… yana <b>{len(pending) - i + 1}</b> ta topshiriq HEMIS'da")
                break
            rows.append(row)
        parts[-1] += "\n<blockquote>" + "\n\n".join(rows) + "</blockquote>"
    else:
        parts[-1] += "\n<i>Topshirilmagan topshiriq yo'q 👏</i>"
    if done:
        parts.append("✅ <b>Topshirilgan:</b>\n" + "\n".join(f"• {_e(t.name)}" for t in done))
    if missed:
        parts.append("❌ <b>Muddati o'tgan:</b>\n" + "\n".join(
            f"• {_e(t.name)} — {_deadline(t)}" for t in missed))
    parts.append("<i>Yuklash: HEMIS → O'quv reja → Fanlar resurslari</i>")
    return "\n\n".join(parts)


def task_reminder(t: Task, current: datetime) -> str:
    return (
        "⏰ <b>Topshiriq muddati yaqinlashmoqda!</b>\n\n"
        f"<blockquote>{_task_row(t, current, with_subject=True)}</blockquote>\n\n"
        "Hali yuklamadingiz. HEMIS → Fanlar resurslari bo'limidan yuklang."
    )


def new_task(t: Task, current: datetime) -> str:
    return (
        "🆕 <b>Yangi topshiriq berildi!</b>\n\n"
        f"<blockquote>{_task_row(t, current, with_subject=True)}</blockquote>"
    )


def profile(p: dict) -> str:
    """Rasm izohi sifatida ham ishlatiladi (Telegram chegarasi 1024 belgi)."""
    form = " · ".join(x for x in (p["education_form"], p["education_type"]) if x)
    course = " · ".join(x for x in (p["level"], p["semester"]) if x)
    sections = [
        f"👤 <b>{_e(p['full_name'])}</b>",
        _section("🏛 <b>TA'LIM MUASSASASI</b>", [
            ("Universitet", p["university"]),
            ("Fakultet", p["faculty"]),
            ("Yo'nalish", p["specialty"]),
        ]),
        _section("🎓 <b>O'QISH</b>", [
            ("Talaba ID", p["student_id"]),
            ("Guruh", p["group"]),
            ("Kurs", course),
            ("Ta'lim shakli", form),
            ("To'lov shakli", p["payment_form"]),
            ("Holati", p["status"]),
            ("O'rtacha GPA", p["gpa"] if p["gpa"] not in ("0", "0.0", "0.00") else ""),
        ]),
    ]
    return "\n\n".join(s for s in sections if s)


def notify_settings(enabled: bool, minutes: int, morning_time: str) -> str:
    if not enabled:
        return "🔕 <b>Eslatmalar o'chirilgan</b>\n\nYoqish uchun pastdagi tugmani bosing."
    return (
        "🔔 <b>Eslatmalar yoqilgan</b>\n\n"
        f"☀️ Har kuni <b>{morning_time}</b> da bugungi darslar ro'yxati\n"
        f"⏰ Har bir darsdan <b>{minutes} daqiqa</b> oldin xona va vaqt\n"
        "🚨 NB qo'yilsa — darhol xabar\n"
        "📚 Topshiriq muddatidan 3 kun, 1 kun va 3 soat oldin\n\n"
        "Necha daqiqa oldin eslatilsin?"
    )
