import html
import logging
import traceback

import database as db

logger = logging.getLogger(__name__)

_MAX_TRACEBACK_CHARS = 3000


async def notify_admin_error(bot, context: str, exc: BaseException):
    """Kutilmagan xatolik yuz berganda:
    1) har doim logga yozadi (admin_group_id sozlanmagan bo'lsa ham),
    2) admin_group_id sozlangan bo'lsa, o'sha guruhga qisqacha xabar yuboradi.

    `context` — xatolik qayerda yuz berganini bildiruvchi qisqa yorliq,
    masalan: "handler:booking_confirm" yoki "scheduler:check_reminders".

    Bu funksiya hech qachon o'zi exception ko'tarmaydi — chaqirgan joyni
    hech qachon buzmasligi kerak (xatolikni bildirish urinishi yana bir
    xatolikka olib kelmasin)."""
    logger.exception("Xatolik [%s]: %s", context, exc)

    try:
        admin_group_id = await db.get_setting("admin_group_id")
    except Exception:
        logger.exception("admin_group_id ni o'qib bo'lmadi")
        return

    if not admin_group_id:
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

    try:
        await bot.send_message(int(admin_group_id), text)
    except Exception:
        logger.exception("Admin guruhga xatolik xabarini yuborib bo'lmadi")
