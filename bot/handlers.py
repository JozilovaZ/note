from datetime import date, timedelta
from html import escape

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, CallbackQuery, Message, ReplyKeyboardRemove

from bot import keyboards as kb
from config import HEMIS_URL, MORNING_TIME, REMIND_BEFORE
from db import database as db
from hemis import client as hemis
from services import formatter
from services.scheduler import check_absences, now, refresh_user, sync_tasks

router = Router()

NOT_LOGGED_IN = "Avval HEMIS'ga kiring: /start"
SESSION_EXPIRED = "⚠️ HEMIS sessiyangiz tugadi. /start bosib qayta kiring."
HEMIS_DOWN = "⚠️ HEMIS hozir javob bermayapti, keyinroq urinib ko'ring."


class Login(StatesGroup):
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
        return await fetch(db.decrypt_token(user["token"]))
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
        "Parol <b>saqlanmaydi</b> va xabaringiz chatdan darhol o'chiriladi.\n\n"
        "HEMIS <b>loginingizni</b> yuboring (talaba ID):",
        reply_markup=ReplyKeyboardRemove(),
    )
    await state.set_state(Login.login)


@router.message(Login.login, F.text)
async def got_login(message: Message, state: FSMContext):
    await state.update_data(login=message.text.strip())
    await state.set_state(Login.password)
    await message.answer("Endi <b>parolingizni</b> yuboring:")


@router.message(Login.password, F.text)
async def got_password(message: Message, state: FSMContext, bot: Bot):
    password = message.text
    try:
        await message.delete()
    except Exception:
        pass
    username = (await state.get_data())["login"]
    wait = await message.answer("⏳ HEMIS'ga kirilmoqda...")

    try:
        token = await hemis.login(username, password)
        profile = await hemis.get_profile(token)
    except hemis.LoginError:
        await wait.edit_text("❌ Login yoki parol noto'g'ri. Qaytadan /start bosing.")
        await state.clear()
        return
    except hemis.HemisError as e:
        await wait.edit_text(f"⚠️ HEMIS bilan bog'lanib bo'lmadi, keyinroq urinib ko'ring.\n<i>{escape(str(e))}</i>")
        await state.clear()
        return
    finally:
        del password

    await state.clear()
    await db.save_user(message.from_user.id, username, token, profile["full_name"], profile["group"])
    await refresh_user(bot, message.from_user.id)
    await check_absences(bot, message.from_user.id)  # mavjud NB'larni eslab qoladi
    await sync_tasks(bot, message.from_user.id)  # mavjud topshiriqlarni eslab qoladi
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

async def _week_view(user, monday: date):
    today = now().date()
    sunday = monday + timedelta(days=6)
    lessons = await db.get_lessons(user["telegram_id"], monday, sunday)
    bounds = await db.lesson_days(user["telegram_id"])
    keyboard = kb.week_nav(
        monday,
        has_prev=bool(bounds) and bounds[0] < monday,
        has_next=bool(bounds) and bounds[1] > sunday,
        is_current=monday <= today <= sunday,
    )
    return formatter.week_schedule(monday, lessons, today, user["group_name"] or ""), keyboard


def _this_monday() -> date:
    today = now().date()
    return today - timedelta(days=today.weekday())


@router.message(Command("hafta"))
@router.message(F.text == kb.WEEK)
async def week(message: Message):
    if user := await _user_or_reply(message):
        text, keyboard = await _week_view(user, _this_monday())
        await message.answer(text, reply_markup=keyboard)


@router.callback_query(F.data.startswith("week:"))
async def week_page(callback: CallbackQuery):
    user = await db.get_user(callback.from_user.id)
    if not user:
        await callback.answer(NOT_LOGGED_IN, show_alert=True)
        return
    value = callback.data.split(":", 1)[1]
    monday = _this_monday() if value == "now" else date.fromordinal(int(value))
    text, keyboard = await _week_view(user, monday)
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
    tasks = await sync_tasks(bot, message.from_user.id, notify_new=False)
    if tasks is None:
        user = await db.get_user(message.from_user.id)
        await wait.edit_text(HEMIS_DOWN if user and user["token"] else SESSION_EXPIRED)
        return
    await wait.edit_text(
        formatter.tasks_overview(tasks, now()),
        reply_markup=kb.hemis_link(HEMIS_URL),
        disable_web_page_preview=True,
    )


# ---------- Davomat va profil ----------

@router.message(Command("davomat"))
@router.message(F.text == kb.ATTENDANCE)
async def attendance(message: Message):
    if not (user := await _user_or_reply(message)):
        return
    absences = await _from_hemis(message, user, hemis.get_attendance)
    if absences is not None:
        await message.answer(formatter.attendance(absences, user["group_name"] or ""))


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
