import html
import logging
import traceback

import database as db

logger = logging.getLogger(__name__)

_MAX_TRACEBACK_CHARS = 3000


async def notify_admin_error(bot, context: str, exc: BaseException):
    """Kutilmagan xatolik yuz berganda:
    1) har doim logga yozadi,
    2) ro'yxatdagi HAR BIR adminga shaxsan (shaxsiy xabar sifatida) qisqacha
       xabar yuboradi — guruhga emas, to'g'ridan-to'g'ri adminning o'ziga.

    `context` — xatolik qayerda yuz berganini bildiruvchi qisqa yorliq,
    masalan: "handler:booking_confirm" yoki "scheduler:check_reminders".

    Bu funksiya hech qachon o'zi exception ko'tarmaydi — chaqirgan joyni
    hech qachon buzmasligi kerak (xatolikni bildirish urinishi yana bir
    xatolikka olib kelmasin)."""
    logger.exception("Xatolik [%s]: %s", context, exc)

    try:
        admins = await db.list_admins()
    except Exception:
        logger.exception("Adminlar ro'yxatini o'qib bo'lmadi")
        return

    if not admins:
        return

    tb_text = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    if len(tb_text) > _MAX_TRACEBACK_CHARS:
        tb_text = "...\n" + tb_text[-_MAX_TRACEBACK_CHARS:]

    text = (
        "🛑 <b>Botda xatolik yuz berdi</b>\n\n"
        f"Joyi: <code>{html.escape(context)}</code>\n"
        f"Turi: <code>{html.escape(type(exc).__name__)}</code>\n"
        f"Xabar: <code>{html.escape(str(exc))[:500]}</code>\n\n"
        f"<pre>{html.escape(tb_text)}</pre>"
    )

    for admin in admins:
        try:
            await bot.send_message(admin["telegram_id"], text)
        except Exception:
            logger.exception("Adminga (%s) xatolik xabarini yuborib bo'lmadi", admin["telegram_id"])
