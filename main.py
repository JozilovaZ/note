import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

from bot.handlers import router
from config import BOT_TOKEN
from db import database as db
from services import scheduler

COMMANDS = [
    BotCommand(command="hafta", description="Haftalik dars jadvali"),
    BotCommand(command="resurslar", description="Fan resurslari: topshiriqlar va muddatlar"),
    BotCommand(command="davomat", description="Qoldirilgan darslar"),
    BotCommand(command="gpa", description="GPA va akademik qarzdorlik"),
    BotCommand(command="profil", description="Profil"),
    BotCommand(command="eslatma", description="Eslatma sozlamalari"),
    BotCommand(command="chiqish", description="Ma'lumotlarimni o'chirish"),
]


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    # aiohttp so'rov loglarida login/parol chiqmasligi uchun
    logging.getLogger("aiohttp").setLevel(logging.WARNING)

    await db.init()
    bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.include_router(router)
    await bot.set_my_commands(COMMANDS)

    reminders = asyncio.create_task(scheduler.run(bot))
    try:
        await dp.start_polling(bot)
    finally:
        reminders.cancel()
        await db.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
