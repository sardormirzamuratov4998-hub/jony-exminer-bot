import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv

from handlers import registration, booking, exam_flow, admin
import database as db
from scheduler import start_scheduler

load_dotenv()

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
INITIAL_ADMIN_ID = os.getenv("INITIAL_ADMIN_ID")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN topilmadi! .env fayliga yoki Railway Variables ga qo'shing.")


async def main():
    await db.init_db()

    if INITIAL_ADMIN_ID and INITIAL_ADMIN_ID.strip().isdigit():
        await db.add_admin(int(INITIAL_ADMIN_ID.strip()), full_name="Birinchi admin (bootstrap)")
        logging.info(f"Bootstrap admin qo'shildi: {INITIAL_ADMIN_ID}")

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())

    dp.include_router(admin.router)
    dp.include_router(registration.router)
    dp.include_router(booking.router)
    dp.include_router(exam_flow.router)

    start_scheduler(bot)

    await bot.delete_webhook(drop_pending_updates=True)
    logging.info("Bot ishga tushdi (polling)...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
