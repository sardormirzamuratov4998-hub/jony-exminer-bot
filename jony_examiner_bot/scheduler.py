import logging
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

import database as db
from error_notify import notify_admin_error

logger = logging.getLogger(__name__)


def _parse_dt(exam_date: str, exam_time: str) -> datetime:
    return datetime.strptime(f"{exam_date} {exam_time}", "%d.%m.%Y %H:%M")


def _format_hours(hours: float) -> str:
    if hours == int(hours) and hours >= 1:
        return f"{int(hours)} soat"
    total_minutes = round(hours * 60)
    if total_minutes < 60:
        return f"{total_minutes} daqiqa"
    h, m = divmod(total_minutes, 60)
    return f"{h} soat {m} daqiqa" if m else f"{h} soat"


async def check_reminders(bot):
    now = db.now_tashkent()

    hours_str = await db.get_setting("reminder_hours_before")
    try:
        hours_before = float(hours_str) if hours_str else 1.0
    except (TypeError, ValueError):
        hours_before = 1.0
    if hours_before <= 0:
        hours_before = 1.0
    target_minutes = hours_before * 60
    label = _format_hours(hours_before)

    bookings = await db.get_accepted_bookings_needing_reminder()
    for b in bookings:
        try:
            exam_dt = _parse_dt(b["exam_date"], b["exam_time"])
        except ValueError:
            continue

        minutes_left = (exam_dt - now).total_seconds() / 60
        if not b["reminder_1h_sent"] and (target_minutes - 5) <= minutes_left <= (target_minutes + 5):
            try:
                await bot.send_message(
                    b["examiner_telegram_id"],
                    f"⏰ Eslatma: {label}dan so'ng imtihon bor!\n\n"
                    f"Ustoz: {b['teacher_name']}\nFilial: {b['branch']}\n"
                    f"Sana: {b['exam_date']}\nVaqt: {b['exam_time']}\n"
                    f"Guruh: {b['group_name']}",
                )
            except Exception:
                logger.exception("Eslatma yuborilmadi")
            await db.mark_reminder_sent(b["id"], "1h")

        if not b["reminder_time_sent"] and -5 <= minutes_left <= 5:
            try:
                await bot.send_message(
                    b["examiner_telegram_id"],
                    f"🔔 Imtihon vaqti keldi!\n\n"
                    f"Ustoz: {b['teacher_name']}\nFilial: {b['branch']}\n"
                    f"Guruh: {b['group_name']}",
                )
            except Exception:
                logger.exception("Vaqt eslatmasi yuborilmadi")
            await db.mark_reminder_sent(b["id"], "time")


async def check_escalations(bot):
    """Har kuni soat 18:00da (Toshkent vaqti) hali qabul qilinmagan
    barcha buyurtmalar haqida shu filial examinerlarini ogohlantiradi."""
    stale = await db.get_all_pending_bookings()
    for b in stale:
        examiners = await db.get_examiners_by_branch(b["branch"])
        text = (
            f"⚠️ <b>DIQQAT: hali qabul qilinmagan buyurtma bor</b>\n\n"
            f"Ustoz: {b['teacher_name']}\nFilial: {b['branch']}\n"
            f"Sana: {b['exam_date']}\nVaqt: {b['exam_time']}\n"
            f"Guruh: {b['group_name']}"
        )
        for ex in examiners:
            try:
                await bot.send_message(ex["telegram_id"], text)
            except Exception:
                pass

        admin_group_id = await db.get_setting("admin_group_id")
        if admin_group_id:
            try:
                await bot.send_message(int(admin_group_id), text)
            except Exception:
                pass

        await db.mark_escalated(b["id"])


async def check_expired_bookings(bot):
    """Imtihon sanasi o'tib ketgan buyurtmalarni 'expired' deb belgilaydi.
    Hech kim qabul qilmagan (pending holatda muddati o'tgan) buyurtmalar uchun:
    - barcha yuborilgan xabarlardagi 'qabul qilish' tugmasi olib tashlanadi
    - shu filial examinerlariga va admin guruhga jiddiy ogohlantirish yuboriladi."""
    expired_unaccepted = await db.expire_past_bookings()

    for b in expired_unaccepted:
        notifications = await db.get_notifications(b["id"])
        for note in notifications:
            try:
                await bot.edit_message_reply_markup(
                    chat_id=note["chat_id"], message_id=note["message_id"], reply_markup=None
                )
            except Exception:
                pass

        text = (
            f"🚨 <b>DIQQAT! IMTIHON VAQTI O'TIB KETDI!</b>\n\n"
            f"Ustoz: {b['teacher_name']}\n"
            f"Filial: {b['branch']}\n"
            f"Sana: {b['exam_date']}\n"
            f"Vaqt: {b['exam_time']}\n"
            f"Guruh: {b['group_name']}\n\n"
            f"❗️Bu imtihonni hech bir examiner qabul qilmadi va belgilangan vaqt "
            f"allaqachon o'tib ketdi!"
        )

        examiners = await db.get_examiners_by_branch(b["branch"])
        for ex in examiners:
            try:
                await bot.send_message(ex["telegram_id"], text)
            except Exception:
                pass

        admin_group_id = await db.get_setting("admin_group_id")
        if admin_group_id:
            try:
                await bot.send_message(int(admin_group_id), text)
            except Exception:
                pass

    if expired_unaccepted:
        logger.info(f"{len(expired_unaccepted)} ta buyurtma muddati o'tgani uchun 'expired' qilindi")


async def send_daily_report(bot):
    """Har kuni soat 18:00 da admin guruhga kunlik hisobot yuboradi."""
    from handlers.admin import _send_daily_report

    admin_group_id = await db.get_setting("admin_group_id")
    if not admin_group_id:
        logger.info("Kunlik hisobot yuborilmadi: admin_group_id sozlanmagan")
        return

    async def send(text, **kwargs):
        await bot.send_message(int(admin_group_id), text, **kwargs)

    try:
        await _send_daily_report(send)
    except Exception:
        logger.exception("Kunlik hisobot yuborishda xatolik")


def _safe_job(func):
    """APScheduler ichidagi vazifalar aiogramning global xato ushlagichidan
    tashqarida ishlaydi — shuning uchun ularni alohida o'raymiz: xatolik chiqsa
    job "jimgina" o'lib qolmaydi, log qilinadi va admin guruhga xabar boradi."""
    async def wrapper(bot):
        try:
            await func(bot)
        except Exception as e:
            await notify_admin_error(bot, f"scheduler:{func.__name__}", e)
    wrapper.__name__ = f"safe_{func.__name__}"
    return wrapper


def start_scheduler(bot):
    scheduler = AsyncIOScheduler()
    scheduler.add_job(_safe_job(check_reminders), "interval", minutes=1, args=[bot])
    scheduler.add_job(_safe_job(check_expired_bookings), "interval", minutes=10, args=[bot])
    scheduler.add_job(
        _safe_job(send_daily_report),
        CronTrigger(hour=18, minute=0, timezone=db.TASHKENT_TZ),
        args=[bot],
    )
    scheduler.add_job(
        _safe_job(check_escalations),
        CronTrigger(hour=18, minute=0, timezone=db.TASHKENT_TZ),
        args=[bot],
    )
    scheduler.start()
    return scheduler
