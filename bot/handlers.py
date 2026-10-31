import logging
import re
from collections import Counter
from datetime import date, datetime, timedelta
from html import escape

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, CallbackQuery, Message, ReplyKeyboardRemove

from bot import keyboards as kb
from config import ABSENCE_LIMIT, MORNING_TIME, REMIND_BEFORE, UNIVERSITIES
from db import database as db
from hemis import client as hemis
from services import formatter
from services.scheduler import check_absences, check_gpa, now, refresh_user, sync_tasks

router = Router()
log = logging.getLogger(__name__)

NOT_LOGGED_IN = "Avval HEMIS'ga kiring: /start"
SESSION_EXPIRED = "⚠️ HEMIS sessiyangiz tugadi. /start bosib qayta kiring."
HEMIS_DOWN = "⚠️ HEMIS hozir javob bermayapti, keyinroq urinib ko'ring."


class Login(StatesGroup):
    university = State()
    login = State()
    password = State()


async def _user_or_reply(message: Message):
    user = await db.get_user(message.from_user.id)
    if not user or not user["token"]:
        await message.answer(NOT_LOGGED_IN)
        return None
    return user


async def _from_hemis(message: Message, user, fetch):
    """HEMIS'dan jonli ma'lumot oladi; xato bo'lsa foydalanuvchiga yozib None qaytaradi."""
    try:
        return await fetch(db.auth(user))
    except hemis.TokenExpired:
        await db.invalidate_token(user["telegram_id"])
        await message.answer(SESSION_EXPIRED)
    except hemis.HemisError:
        await message.answer(HEMIS_DOWN)
    return None


# ---------- Kirish ----------

@router.message(CommandStart())
async def start(message: Message, state: FSMContext):
    await state.clear()
    user = await db.get_user(message.from_user.id)
    if user and user["token"]:
        await message.answer(f"Salom, {escape(user['full_name'] or '')}! 👋", reply_markup=kb.main)
        return
    await message.answer(
        "Salom! Men dars jadvalingizni eslatib turaman: qaysi dars, qaysi xonada, soat nechida.\n\n"
        "🔐 Login va parolingiz faqat HEMIS'ga kirish uchun ishlatiladi. "
        "Parol <b>saqlanmaydi</b> va xabaringiz chatdan darhol o'chiriladi.",
        reply_markup=ReplyKeyboardRemove(),
    )
    await message.answer(kb.universities_text(), reply_markup=kb.universities())
    await state.set_state(Login.university)


@router.callback_query(Login.university, F.data.startswith("uni:"))
async def got_university(callback: CallbackQuery, state: FSMContext):
    code = callback.data.split(":", 1)[1]
    if code not in UNIVERSITIES:
        await callback.answer()
        return
    await state.update_data(university=code)
    await state.set_state(Login.login)
    await callback.message.edit_text(f"🏛 Universitet: <b>{escape(UNIVERSITIES[code].name)}</b>")
    await callback.message.answer("HEMIS <b>loginingizni</b> yuboring (talaba ID):")
    await callback.answer()


@router.callback_query(Login.password, F.data == kb.CHANGE_LOGIN)
async def change_login(callback: CallbackQuery, state: FSMContext):
    await state.set_state(Login.login)
    await callback.message.answer("HEMIS <b>loginingizni</b> yuboring (talaba ID):")
    await callback.answer()


@router.message(Login.university)
async def university_not_chosen(message: Message):
    await message.answer("Universitetingizni pastdagi tugmalardan tanlang 👇", reply_markup=kb.universities())


@router.message(Login.login, F.text)
async def got_login(message: Message, state: FSMContext):
    username = message.text.strip()
    if re.fullmatch(r"[\d\s-]+", username):
        username = re.sub(r"[\s-]", "", username)  # "3122 2110 0123" -> "312221100123"
    await state.update_data(login=username)
    await state.set_state(Login.password)
    hint = "" if username.isdigit() else (
        "\n\n⚠️ Login odatda faqat raqamlardan iborat <b>talaba ID</b> bo'ladi "
        "(HEMIS profilida yozilgan). Noto'g'ri bo'lsa, /start bosib qaytadan boshlang."
    )
    await message.answer(f"Endi <b>parolingizni</b> yuboring:{hint}")


RATE_LIMIT_PAUSE = timedelta(minutes=5)
_rate_limited_until: dict[str, datetime] = {}  # universitet -> HEMIS'ga qayta urinish mumkin bo'lgan vaqt


def _rate_limited_text(until: datetime) -> str:
    return (
        "⏳ HEMIS ko'p kirish urinishlari sababli botga vaqtincha cheklov qo'ydi. "
        "Bu sizning parolingiz bilan bog'liq emas.\n\n"
        f"Iltimos, <b>{until:%H:%M}</b> dan keyin <b>parolingizni</b> qayta yuboring."
    )


def _mask(username: str) -> str:
    return f"{'*' * max(len(username) - 3, 0)}{username[-3:]} (uzunligi {len(username)})"


@router.message(Login.password, F.text)
async def got_password(message: Message, state: FSMContext, bot: Bot):
    password = message.text
    try:
        await message.delete()
    except Exception:
        pass
    data = await state.get_data()
    username, university = data["login"], data["university"]
    url = UNIVERSITIES[university].url
    until = _rate_limited_until.get(university)
    if until and now() < until:
        # cheklov paytida urinish uni uzaytiradi, shuning uchun HEMIS'ga yubormaymiz
        await message.answer(_rate_limited_text(until), reply_markup=kb.wrong_password)
        return
    wait = await message.answer("⏳ HEMIS'ga kirilmoqda...")

    try:
        token = await hemis.login(url, username, password)
        profile = await hemis.get_profile(hemis.Auth(url, token))
    except hemis.RateLimited:
        until = _rate_limited_until[university] = now() + RATE_LIMIT_PAUSE
        log.warning("Login: %s HEMIS'i captcha talab qilyapti (429), kirish %s gacha to'xtatildi",
                    university, f"{until:%H:%M}")
        await wait.edit_text(_rate_limited_text(until), reply_markup=kb.wrong_password)
        return  # holat Login.password'da qoladi, keyin faqat parolni yuborish kifoya
    except hemis.LoginError:
        log.info("Login xato: user=%s uni=%s login=%s", message.from_user.id, university, _mask(username))
        await wait.edit_text(
            f"❌ <b>{escape(UNIVERSITIES[university].short)}</b> HEMIS'i login yoki parolni qabul qilmadi.\n\n"
            "Tekshiring:\n"
            "• Universitet to'g'ri tanlanganmi? Noto'g'ri bo'lsa, /start bosing.\n"
            "• Login — talaba ID raqami (ism yoki telefon emas).\n"
            "• Parolda katta-kichik harf farq qiladi. Telefon birinchi harfni o'zi katta qilib "
            "qo'ymaganini tekshiring.\n"
            "• HEMIS saytiga shu login-parol bilan kira olasizmi?\n\n"
            f"Login: <code>{escape(username)}</code>\n"
            "<b>Parolingizni</b> qaytadan kiriting:",
            reply_markup=kb.wrong_password,
        )
        await state.set_state(Login.password)  # login va universitet saqlanadi
        return
    except hemis.ApiError as e:
        log.warning("Login rad etildi: user=%s uni=%s login=%s xato=%s",
                    message.from_user.id, university, _mask(username), e)
        await wait.edit_text(f"❌ HEMIS kirishni rad etdi:\n<i>{escape(str(e))}</i>\n\n"
                             "Bu HEMIS tomonidagi cheklov, dekanat yoki tyutoringizga murojaat qiling.")
        await state.clear()
        return
    except hemis.HemisError as e:
        log.warning("Login: HEMIS ishlamadi: user=%s uni=%s xato=%s", message.from_user.id, university, e)
        await wait.edit_text(f"⚠️ HEMIS bilan bog'lanib bo'lmadi, keyinroq urinib ko'ring.\n<i>{escape(str(e))}</i>")
        await state.clear()
        return
    finally:
        del password

    await state.clear()
    await db.save_user(message.from_user.id, university, username, token, profile["full_name"], profile["group"])
    await refresh_user(bot, message.from_user.id)
    await check_absences(bot, message.from_user.id)  # mavjud NB'larni eslab qoladi
    await sync_tasks(bot, message.from_user.id)  # mavjud topshiriqlarni eslab qoladi
    await check_gpa(bot, message.from_user.id)  # joriy GPA'ni eslab qoladi
    await wait.delete()
    await message.answer(
        f"✅ Xush kelibsiz, <b>{escape(profile['full_name'])}</b>!\n"
        f"Guruh: {escape(profile['group'])}\n\n"
        f"Har kuni {MORNING_TIME} da bugungi darslarni, har bir darsdan oldin "
        "xona va vaqtni eslatib turaman. Sizga NB qo'yilsa, darhol xabar beraman.",
        reply_markup=kb.main,
    )


@router.message(Command("chiqish"))
async def logout(message: Message, state: FSMContext):
    await state.clear()
    await db.delete_user(message.from_user.id)
    await message.answer(
        "Barcha ma'lumotlaringiz o'chirildi. Qayta foydalanish uchun /start bosing.",
        reply_markup=ReplyKeyboardRemove(),
    )


# ---------- Haftalik jadval ----------

async def _week_view(user, monday: date, selected: date | None = None):
    today = now().date()
    sunday = monday + timedelta(days=6)
    lessons = await db.get_lessons(user["telegram_id"], monday, sunday)
    bounds = await db.lesson_days(user["telegram_id"])
    counts = Counter(l.day for l in lessons)
    keyboard = kb.week_days(
        monday, counts, today, selected,
        has_prev=bool(bounds) and bounds[0] < monday,
        has_next=bool(bounds) and bounds[1] > sunday,
        is_current=monday <= today <= sunday,
    )
    text = formatter.week_schedule(monday, lessons, today, user["group_name"] or "", selected)
    return text, keyboard


def _this_monday() -> date:
    today = now().date()
    return today - timedelta(days=today.weekday())


@router.message(Command("hafta"))
@router.message(F.text == kb.WEEK)
async def week(message: Message):
    if user := await _user_or_reply(message):
        text, keyboard = await _week_view(user, _this_monday())
        await message.answer(text, reply_markup=keyboard)


@router.callback_query(F.data.startswith(("week:", "day:")))
async def week_page(callback: CallbackQuery):
    user = await db.get_user(callback.from_user.id)
    if not user:
        await callback.answer(NOT_LOGGED_IN, show_alert=True)
        return
    action, value = callback.data.split(":", 1)
    if action == "day":
        selected = date.fromordinal(int(value))
        monday = selected - timedelta(days=selected.weekday())
    else:
        selected = None
        monday = _this_monday() if value == "now" else date.fromordinal(int(value))
    text, keyboard = await _week_view(user, monday, selected)
    if callback.message.photo:
        # eski versiyadagi rasmli xabar: matnga almashtirib bo'lmaydi, yangisini yuboramiz
        await callback.message.delete()
        await callback.message.answer(text, reply_markup=keyboard)
    else:
        try:
            await callback.message.edit_text(text, reply_markup=keyboard)
        except TelegramBadRequest:
            pass  # xabar o'zgarmagan
    await callback.answer()


# ---------- Fan resurslari ----------

@router.message(Command("resurslar"))
@router.message(F.text == kb.RESOURCES)
async def resources(message: Message, bot: Bot):
    if not await _user_or_reply(message):
        return
    wait = await message.answer("⏳ Topshiriqlar HEMIS'dan yuklanmoqda...")
    await _show_subjects(wait, bot, message.from_user.id)


async def _show_subjects(target: Message, bot: Bot, telegram_id: int) -> None:
    """HEMIS'dan yangilab, fanlar ro'yxatini ko'rsatadi (target xabarini tahrirlaydi)."""
    tasks = await sync_tasks(bot, telegram_id, notify_new=False)
    user = await db.get_user(telegram_id)
    if tasks is None:
        await target.edit_text(HEMIS_DOWN if user and user["token"] else SESSION_EXPIRED)
        return
    current = now()
    try:
        await target.edit_text(
            formatter.tasks_overview(tasks, current),
            reply_markup=kb.subjects(tasks, current, None, db.university(user).url),
        )
    except TelegramBadRequest:
        pass  # xabar o'zgarmagan


@router.callback_query(F.data.startswith("subj:"))
async def subject_page(callback: CallbackQuery, bot: Bot):
    user = await db.get_user(callback.from_user.id)
    if not user or not user["token"]:
        await callback.answer(NOT_LOGGED_IN, show_alert=True)
        return
    value = callback.data.split(":", 1)[1]
    if value == "refresh":
        await callback.answer("⏳ Yangilanmoqda...")
        await _show_subjects(callback.message, bot, callback.from_user.id)
        return

    subject_id, current = int(value), now()
    tasks = await db.get_tasks(callback.from_user.id)  # tez: HEMIS'ga so'rovsiz, bazadan
    try:
        await callback.message.edit_text(
            formatter.subject_tasks(tasks, subject_id, current),
            reply_markup=kb.subjects(tasks, current, subject_id, db.university(user).url),
            disable_web_page_preview=True,
        )
    except TelegramBadRequest:
        pass  # xabar o'zgarmagan
    await callback.answer()


# ---------- Davomat va profil ----------

@router.message(Command("davomat"))
@router.message(F.text == kb.ATTENDANCE)
async def attendance(message: Message):
    if not (user := await _user_or_reply(message)):
        return
    absences = await _from_hemis(message, user, hemis.get_attendance)
    if absences is not None:
        await message.answer(formatter.attendance(absences, user["group_name"] or "", ABSENCE_LIMIT))


@router.message(Command("gpa"))
@router.message(F.text == kb.GPA)
async def gpa(message: Message):
    if not (user := await _user_or_reply(message)):
        return
    items = await _from_hemis(message, user, hemis.get_gpa)
    if items is not None:
        await message.answer(formatter.gpa(items))


@router.message(Command("profil"))
@router.message(F.text == kb.PROFILE)
async def profile(message: Message):
    if not (user := await _user_or_reply(message)):
        return
    p = await _from_hemis(message, user, hemis.get_profile)
    if p is None:
        return
    text = formatter.profile(p) + "\n\n<i>Ma'lumotlarimni botdan o'chirish: /chiqish</i>"
    photo = await hemis.get_image(p["image"]) if p["image"] else None
    if photo and len(text) <= 1024:  # rasm izohi chegarasi
        await message.answer_photo(BufferedInputFile(photo, filename="profil.jpg"), caption=text)
    else:
        await message.answer(text)


# ---------- Eslatmalar ----------

def _notify_view(user):
    minutes = user["remind_before"] or REMIND_BEFORE
    enabled = bool(user["notify"])
    return (
        formatter.notify_settings(enabled, minutes, MORNING_TIME),
        kb.notify_settings(enabled, minutes),
    )


@router.message(Command("eslatma"))
@router.message(F.text == kb.NOTIFY)
async def notify(message: Message):
    if user := await _user_or_reply(message):
        text, keyboard = _notify_view(user)
        await message.answer(text, reply_markup=keyboard)


@router.callback_query(F.data.startswith(("notify:", "remind:")))
async def notify_change(callback: CallbackQuery):
    action, value = callback.data.split(":", 1)
    tid = callback.from_user.id
    if action == "notify":
        await db.set_notify(tid, value == "on")
    elif int(value) in kb.REMIND_OPTIONS:
        await db.set_remind_before(tid, int(value))

    user = await db.get_user(tid)
    if not user:
        await callback.answer(NOT_LOGGED_IN, show_alert=True)
        return
    text, keyboard = _notify_view(user)
    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except TelegramBadRequest:
        pass
    await callback.answer("Saqlandi ✅")
