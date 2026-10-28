"""Fon vazifalari: jadvalni yangilash, ertalabki xabar, darsdan oldin eslatma va yangi NB xabari."""
import asyncio
import logging
from datetime import datetime, timedelta

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError

from config import ABSENCE_LIMIT, MORNING_TIME, REMIND_BEFORE, TZ
from db import database as db
from hemis import client as hemis
from services import formatter

log = logging.getLogger(__name__)

REFRESH_HOURS = (6, 12, 18)  # jadval shu soatlarda HEMIS'dan yangilanadi
ABSENCE_MINUTES = (0, 30)    # davomat har 30 daqiqada tekshiriladi...
ABSENCE_HOURS = (8, 21)      # ...08:00 dan 21:00 gacha
TASK_HOURS = (8, 11, 14, 17, 20)  # topshiriqlar shu soatlarning 15-daqiqasida yangilanadi
TASK_REMINDERS = (("3d", timedelta(days=3)), ("1d", timedelta(days=1)), ("3h", timedelta(hours=3)))
QUIET_HOURS = (22, 8)        # 22:00–08:00 topshiriq eslatmalari yuborilmaydi
QUIET_ADVANCE = timedelta(hours=1)  # muddati tunda tugasa, eslatma 21:00 da yuboriladi
ABSENCE_WARN_LEVELS = (50, 75, 90, 100)  # sababsiz NB chegaraning shu foizlariga yetganda ogohlantiriladi
RELOGIN_TEXT = (
    "⚠️ HEMIS sessiyangiz tugadi. Eslatmalar davom etishi uchun /start bosib qayta kiring."
)


def now() -> datetime:
    return datetime.now(TZ)


async def refresh_user(bot: Bot, telegram_id: int) -> bool:
    """Foydalanuvchi jadvalini HEMIS'dan yangilaydi. Muvaffaqiyatli bo'lsa True."""
    user = await db.get_user(telegram_id)
    token = db.decrypt_token(user["token"]) if user else None
    if not token:
        return False
    try:
        lessons = await hemis.get_schedule(token)
    except hemis.TokenExpired:
        await db.invalidate_token(telegram_id)
        await _send(bot, telegram_id, RELOGIN_TEXT)
        return False
    except hemis.HemisError as e:
        log.warning("Jadval yangilanmadi (%s): %s", telegram_id, e)
        return False
    await db.replace_lessons(telegram_id, lessons)
    return True


def _absence_key(a: hemis.Absence) -> str:
    return f"{a.day}|{a.subject}|{a.pair}|{a.kind}"


async def check_absences(bot: Bot, telegram_id: int) -> None:
    """Davomatni oldingi holat bilan solishtiradi va yangi NB haqida xabar beradi."""
    user = await db.get_user(telegram_id)
    token = db.decrypt_token(user["token"]) if user else None
    if not token:
        return
    try:
        absences = await hemis.get_attendance(token)
    except hemis.TokenExpired:
        await db.invalidate_token(telegram_id)
        await _send(bot, telegram_id, RELOGIN_TEXT)
        return
    except hemis.HemisError as e:
        log.warning("Davomat tekshirilmadi (%s): %s", telegram_id, e)
        return

    current = {_absence_key(a): a.excused for a in absences}
    # birinchi marta: eski NB'lar uchun xabar yubormasdan faqat eslab qolamiz
    if user["absences_synced"] and user["notify"]:
        known = await db.known_absences(telegram_id)
        semester_total = sum(a.hours for a in absences)
        for a in sorted(absences, key=lambda a: a.day):
            key = _absence_key(a)
            if key not in known:
                subject_total = sum(x.hours for x in absences if x.subject == a.subject)
                await _send(bot, telegram_id, formatter.new_absence(a, subject_total, semester_total))
            elif a.excused and not known[key]:
                await _send(bot, telegram_id, formatter.absence_excused(a))
    await db.save_absences(telegram_id, current)
    if user["notify"]:
        await _warn_absence_limit(bot, telegram_id, absences, user["absence_warned"])


async def _warn_absence_limit(bot: Bot, telegram_id: int, absences: list[hemis.Absence], warned: int) -> None:
    """Sababsiz NB yangi bosqichga (50%, 75%, ...) yetganda bir marta ogohlantiradi."""
    if ABSENCE_LIMIT <= 0:
        return
    unexcused = sum(a.hours for a in absences if not a.excused)
    level = max((p for p in ABSENCE_WARN_LEVELS if unexcused * 100 >= ABSENCE_LIMIT * p), default=0)
    if level > warned:
        await _send(bot, telegram_id, formatter.absence_limit(unexcused, ABSENCE_LIMIT))
    # NB sababli deb belgilansa yoki yangi semestr boshlansa, bosqich pasayadi
    # va keyinchalik qayta oshganda yana ogohlantiriladi
    if level != warned:
        await db.set_absence_warned(telegram_id, level)


async def sync_tasks(bot: Bot, telegram_id: int, notify_new: bool = True) -> list[hemis.Task] | None:
    """Topshiriqlarni HEMIS'dan oladi, yangilari haqida xabar beradi va saqlaydi."""
    user = await db.get_user(telegram_id)
    token = db.decrypt_token(user["token"]) if user else None
    if not token:
        return None
    try:
        tasks = await hemis.get_tasks(token)
    except hemis.TokenExpired:
        await db.invalidate_token(telegram_id)
        await _send(bot, telegram_id, RELOGIN_TEXT)
        return None
    except hemis.HemisError as e:
        log.warning("Topshiriqlar olinmadi (%s): %s", telegram_id, e)
        return None

    # birinchi marta: mavjud topshiriqlar "yangi" deb xabar qilinmaydi
    if notify_new and user["tasks_synced"] and user["notify"]:
        known = await db.known_task_ids(telegram_id)
        current = now()
        for t in tasks:
            if t.id not in known and not t.submitted and t.deadline > current:
                await _send(bot, telegram_id, formatter.new_task(t, current))
    await db.save_tasks(telegram_id, tasks)
    return tasks


def _quiet_start(moment: datetime) -> datetime | None:
    """moment tinch soatlarga tushsa, o'sha tunning boshlanish vaqti (22:00)."""
    start = moment.replace(hour=QUIET_HOURS[0], minute=0, second=0, microsecond=0)
    if moment.hour >= QUIET_HOURS[0]:
        return start
    if moment.hour < QUIET_HOURS[1]:
        return start - timedelta(days=1)
    return None


def _remind_at(deadline: datetime, delta: timedelta) -> datetime:
    """Eslatma vaqti. Muddat tunda tugasa, tunga tushgan eslatma kechqurunga suriladi,
    aks holda u ertalabgacha kutib, muddatdan keyin qolib ketardi."""
    at = deadline - delta
    quiet = _quiet_start(deadline)
    if quiet and at > quiet - QUIET_ADVANCE:
        at = quiet - QUIET_ADVANCE
    return at


async def _remind_tasks(bot: Bot, telegram_id: int, current: datetime) -> None:
    for t in await db.pending_tasks(telegram_id, current):
        due = [label for label, delta in TASK_REMINDERS if current >= _remind_at(t.deadline, delta)]
        if not due:
            continue
        # birdaniga bir nechta chegara o'tgan bo'lsa (masalan topshiriq kech qo'shilgan),
        # faqat bitta xabar yuborib, qolganlarini ham yuborilgan deb belgilaymiz
        fresh = [label for label in due if await db.mark_sent(telegram_id, f"{t.deadline:%Y-%m-%d}|task|{t.id}|{label}")]
        if fresh:
            await _send(bot, telegram_id, formatter.task_reminder(t, current))


async def _send(bot: Bot, telegram_id: int, text: str) -> None:
    try:
        await bot.send_message(telegram_id, text)
    except TelegramForbiddenError:
        # foydalanuvchi botni bloklagan
        await db.set_notify(telegram_id, False)
    except Exception:
        log.exception("Xabar yuborilmadi: %s", telegram_id)


async def _sync_all(bot: Bot, telegram_ids: list[int], schedule: bool = False,
                    absences: bool = False, tasks: bool = False) -> None:
    for tid in telegram_ids:
        if schedule:
            await refresh_user(bot, tid)
        if absences:
            await check_absences(bot, tid)
        if tasks:
            await sync_tasks(bot, tid)
        await asyncio.sleep(1)  # HEMIS'ni ortiqcha yuklamaslik uchun


async def _tick(bot: Bot) -> None:
    current = now()
    today = current.date()
    hhmm = current.strftime("%H:%M")

    if hhmm == "00:05":
        await db.cleanup_sent(today)

    users = await db.logged_in_users()

    schedule_due = current.minute == 0 and current.hour in REFRESH_HOURS
    absences_due = current.minute in ABSENCE_MINUTES and ABSENCE_HOURS[0] <= current.hour < ABSENCE_HOURS[1]
    tasks_due = current.minute == 15 and current.hour in TASK_HOURS
    if schedule_due or absences_due or tasks_due:
        # alohida vazifada, eslatmalar kechikmasligi uchun
        asyncio.create_task(_sync_all(bot, [u["telegram_id"] for u in users],
                                      schedule_due, absences_due, tasks_due))

    for user in users:
        if not user["notify"]:
            continue
        tid = user["telegram_id"]
        remind_before = user["remind_before"] or REMIND_BEFORE
        lessons = await db.get_lessons(tid, today)

        if hhmm == MORNING_TIME and lessons and await db.mark_sent(tid, f"{today}|morning"):
            await _send(bot, tid, "☀️ Xayrli tong! Bugungi darslaringiz:\n\n"
                        + formatter.day_schedule(today, lessons))

        for lesson in lessons:
            start = datetime.combine(today, datetime.strptime(lesson.start, "%H:%M").time(), TZ)
            if timedelta(0) < start - current <= timedelta(minutes=remind_before):
                if await db.mark_sent(tid, f"{today}|{lesson.start}"):
                    minutes = round((start - current).total_seconds() / 60)
                    await _send(bot, tid, formatter.reminder(lesson, minutes))

        if QUIET_HOURS[1] <= current.hour < QUIET_HOURS[0]:  # kechasi bezovta qilmaymiz
            await _remind_tasks(bot, tid, current)


async def run(bot: Bot) -> None:
    # ishga tushganda davomatni darhol tekshirish (yangi foydalanuvchilar uchun boshlang'ich holat)
    users = await db.logged_in_users()
    asyncio.create_task(_sync_all(bot, [u["telegram_id"] for u in users], absences=True, tasks=True))
    while True:
        try:
            await _tick(bot)
        except Exception:
            log.exception("Rejalashtiruvchida xato")
        # keyingi daqiqa boshigacha kutish
        await asyncio.sleep(60 - now().second + 1)
