import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ErrorEvent
from dotenv import load_dotenv

from handlers import registration, booking, exam_flow, admin
import database as db
from error_notify import notify_admin_error
from scheduler import start_scheduler

load_dotenv()

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
INITIAL_ADMIN_ID = os.getenv("INITIAL_ADMIN_ID")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN topilmadi! .env fayliga yoki Railway Variables ga qo'shing.")

UPDATE_NOTICE_TEXT = (
    "🔄 Bot yangilandi!\n\n"
    "/start bosib botni yangilab, ishlashni davom ettirishingiz mumkin."
)


async def _broadcast_update_notice(bot: Bot):
    """Har deploy (bot qayta ishga tushganda) botdan foydalangan HAMMA odamga
    \"bot yangilandi\" xabarini yuboradi. Fon vazifasi sifatida ishlaydi —
    pollingni to'xtatib turmaydi, bitta odamga yuborilmasa (bloklagan bo'lsa)
    ham qolganlarga davom etadi."""
    try:
        user_ids = await db.get_all_user_ids()
    except Exception:
        logging.exception("Foydalanuvchilar ro'yxatini o'qib bo'lmadi (update notice)")
        return

    sent, failed = 0, 0
    for telegram_id in user_ids:
        try:
            await bot.send_message(telegram_id, UPDATE_NOTICE_TEXT)
            sent += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.05)  # Telegram flood-limitiga tushmaslik uchun sekinlashtirish

    logging.info(f"Yangilanish xabari yuborildi: {sent} ta muvaffaqiyatli, {failed} ta yuborilmadi")


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

    @dp.error()
    async def global_error_handler(event: ErrorEvent):
        """Handlerlar ichida ushlanmagan har qanday xatolik shu yerga tushadi —
        bot yiqilib qolmaydi va admin guruhga xabar boradi."""
        update_id = event.update.update_id if event.update else "?"
        await notify_admin_error(bot, f"handler (update_id={update_id})", event.exception)
        return True

    dp.include_router(admin.router)
    dp.include_router(registration.router)
    dp.include_router(booking.router)
    dp.include_router(exam_flow.router)

    start_scheduler(bot)

    await bot.delete_webhook(drop_pending_updates=True)
    logging.info("Bot ishga tushdi (polling)...")

    # Fon vazifasi sifatida — pollingni kutdirmaydi
    asyncio.create_task(_broadcast_update_notice(bot))

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
