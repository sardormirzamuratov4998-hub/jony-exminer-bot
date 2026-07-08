import logging
from datetime import datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler

import database as db

logger = logging.getLogger(__name__)


def _parse_dt(exam_date: str, exam_time: str) -> datetime:
    return datetime.strptime(f"{exam_date} {exam_time}", "%d.%m.%Y %H:%M")


async def check_reminders(bot):
    now = datetime.now()
    bookings = await db.get_accepted_bookings_needing_reminder()
    for b in bookings:
        try:
            exam_dt = _parse_dt(b["exam_date"], b["exam_time"])
        except ValueError:
            continue

        # 1 soat oldin eslatma (55-65 daqiqa oralig'ida, chunki job har daqiqa ishlamaydi)
        minutes_left = (exam_dt - now).total_seconds() / 60
        if not b["reminder_1h_sent"] and 0 <= minutes_left <= 65 and minutes_left >= 55:
            try:
                await bot.send_message(
                    b["examiner_telegram_id"],
                    f"⏰ Eslatma: 1 soatdan so'ng imtihon bor!\n\n"
                    f"Ustoz: {b['teacher_name']}\nFilial: {b['branch']}\n"
                    f"Sana: {b['exam_date']}\nVaqt: {b['exam_time']}\n"
                    f"Guruh: {b['group_name']}",
                )
            except Exception:
                logger.exception("1 soatlik eslatma yuborilmadi")
            await db.mark_reminder_sent(b["id"], "1h")

        # Imtihon vaqti keldi eslatmasi (0-5 daqiqa oralig'ida)
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
    stale = await db.get_pending_bookings_older_than(24)
    for b in stale:
        examiners = await db.get_examiners_by_branch(b["branch"])
        text = (
            f"⚠️ <b>DIQQAT: 24 soatdan beri qabul qilinmagan buyurtma</b>\n\n"
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


def start_scheduler(bot):
    scheduler = AsyncIOScheduler()
    scheduler.add_job(check_reminders, "interval", minutes=1, args=[bot])
    scheduler.add_job(check_escalations, "interval", minutes=30, args=[bot])
    scheduler.start()
    return scheduler
