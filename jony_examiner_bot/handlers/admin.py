import os
from datetime import datetime

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder

import database as db
from states import AdminStates
from keyboards import (
    examiner_approve_kb,
    admin_panel_kb,
    branch_manage_kb,
    branch_delete_confirm_kb,
    test_type_manage_kb,
    test_type_delete_confirm_kb,
)

router = Router()


class AddAdminStates(StatesGroup):
    waiting_input = State()


async def _require_admin(message: Message) -> bool:
    if not await db.is_admin(message.from_user.id):
        await message.answer("Bu komanda faqat adminlar uchun.")
        return False
    return True


# ---------- YORDAMCHI FUNKSIYALAR (komanda va tugma ikkalasida ham ishlatiladi) ----------

async def _send_pending(send):
    pending = await db.get_pending_examiners()
    if not pending:
        await send("Kutilayotgan examiner so'rovlari yo'q.")
        return
    for p in pending:
        uname = f"@{p['username']}" if p["username"] else "username yo'q"
        await send(
            f"Ism: {p['full_name']}\nFilial: {p['branch']}\nTelegram: {uname}",
            reply_markup=examiner_approve_kb(p["telegram_id"]),
        )


async def _send_bookings(send):
    bookings = await db.get_active_bookings()
    if not bookings:
        await send("Faol buyurtmalar yo'q.")
        return
    for b in bookings:
        status_emoji = "🟡" if b["status"] == "pending" else "🟢"
        examiner = f"\nExaminer: {b['examiner_name']}" if b["examiner_name"] else "\nExaminer: kutilmoqda"
        text = (
            f"{status_emoji} <b>{b['exam_date']} {b['exam_time']}</b>\n"
            f"Filial: {b['branch']}\nUstoz: {b['teacher_name']}\n"
            f"Guruh: {b['group_name']}{examiner}"
        )
        builder = InlineKeyboardBuilder()
        builder.button(text="❌ Bekor qilish", callback_data=f"cancel_booking:{b['id']}")
        builder.adjust(1)
        await send(text, reply_markup=builder.as_markup())


async def _send_staff(send):
    staff = await db.get_all_staff()
    if not staff:
        await send("Hozircha ro'yxatdan o'tgan xodim yo'q.")
        return

    by_branch = {}
    for s in staff:
        by_branch.setdefault(s["branch"], []).append(s)

    for branch, users in by_branch.items():
        lines = [f"📍 <b>{branch}</b>\n"]
        builder = InlineKeyboardBuilder()
        for u in users:
            role_label = "👩‍🏫 Ustoz" if u["role"] == "TEACHER" else "🧑‍💼 Examiner"
            status_label = {
                "active": "", "approved": "", "pending": " (kutilmoqda)", "rejected": " (rad etilgan)",
            }.get(u["status"], "")
            lines.append(f"{role_label}: {u['full_name']}{status_label}")
            builder.button(text=f"❌ {u['full_name']}", callback_data=f"remove_staff:{u['id']}")
        builder.adjust(1)
        await send("\n".join(lines), reply_markup=builder.as_markup())


async def _send_admins(send):
    admins = await db.list_admins()
    if not admins:
        await send("Hozircha adminlar yo'q.")
        return
    lines = ["👤 <b>Adminlar ro'yxati:</b>\n"]
    for a in admins:
        name = a["full_name"] or "Noma'lum"
        uname = f"@{a['username']}" if a["username"] else ""
        lines.append(f"• {name} {uname} — ID: {a['telegram_id']}")
    await send("\n".join(lines))


async def _send_daily_report(send, bot=None):
    today = db.now_tashkent().strftime("%d.%m.%Y")
    report = await db.get_daily_report(today)
    lines = [f"📊 <b>Kunlik hisobot — {today}</b>\n"]

    lines.append("📥 <b>Kelib tushgan buyurtmalar (filial bo'yicha):</b>")
    if report["created_today_by_branch"]:
        for branch, count in report["created_today_by_branch"].items():
            lines.append(f"• {branch}: {count} ta")
    else:
        lines.append("• Bugun buyurtma tushmagan")

    lines.append("\n✅ <b>Qabul qilingan imtihonlar (examiner bo'yicha):</b>")
    if report["accepted_today_by_examiner"]:
        for name, count in report["accepted_today_by_examiner"].items():
            lines.append(f"• {name}: {count} ta")
    else:
        lines.append("• Bugun hech kim imtihon qabul qilmagan")

    await send("\n".join(lines))


async def _send_stats(send, days: int = 30):
    stats = await db.get_stats(days)
    lines = [f"📈 <b>Statistika (oxirgi {days} kun)</b>\n"]

    lines.append(f"📥 Jami buyurtmalar: {stats['total_bookings']} ta")
    lines.append(f"✅ Qabul qilingan: {stats['accepted_bookings']} ta")
    if stats["total_bookings"]:
        rate = stats["accepted_bookings"] / stats["total_bookings"] * 100
        lines.append(f"📊 Qabul qilish darajasi: {rate:.0f}%")

    if stats["by_branch"]:
        lines.append("\n📍 <b>Filial bo'yicha buyurtmalar:</b>")
        for branch, count in stats["by_branch"].items():
            lines.append(f"• {branch}: {count} ta")

    if stats["by_examiner"]:
        lines.append("\n🧑‍💼 <b>Examinerlar bo'yicha o'tkazilgan testlar:</b>")
        for name, info in stats["by_examiner"].items():
            lines.append(f"• {name}: {info['count']} ta test, o'rtacha {info['avg_percent']:.0f}%")

    if stats["overall_avg_percent"] is not None:
        lines.append(f"\n🎯 Umumiy o'rtacha ball: {stats['overall_avg_percent']:.0f}%")
        lines.append(f"✅ PASS: {stats['total_pass']} ta   ❌ FAIL: {stats['total_fail']} ta")
    else:
        lines.append("\nHali natija statistikasi yo'q (test yakunlanmagan).")

    await send("\n".join(lines))


# ---------- KOMANDALAR ----------

@router.message(Command("admin_group"))
async def set_admin_group(message: Message):
    if not await _require_admin(message):
        return
    if message.chat.type not in ("group", "supergroup"):
        await message.answer("Bu komanda faqat guruhda ishlaydi.")
        return
    await db.set_setting("admin_group_id", str(message.chat.id))
    await message.answer(f"✅ Bu guruh admin guruh sifatida belgilandi.\nChat ID: {message.chat.id}")


@router.message(Command("add_admin"))
async def add_admin_start(message: Message, state: FSMContext):
    if not await _require_admin(message):
        return
    await state.set_state(AddAdminStates.waiting_input)
    await message.answer(
        "Yangi adminning Telegram ID sini yuboring,\n"
        "yoki undan (yoki u yuborgan istalgan xabarni) forward qiling."
    )


@router.callback_query(F.data == "admin_add")
async def add_admin_start_cb(callback: CallbackQuery, state: FSMContext):
    if not await db.is_admin(callback.from_user.id):
        await callback.answer("Bu tugma faqat adminlar uchun.", show_alert=True)
        return
    await state.set_state(AddAdminStates.waiting_input)
    await callback.message.answer(
        "Yangi adminning Telegram ID sini yuboring,\n"
        "yoki undan (yoki u yuborgan istalgan xabarni) forward qiling."
    )
    await callback.answer()


@router.message(AddAdminStates.waiting_input)
async def add_admin_process(message: Message, state: FSMContext):
    await state.clear()
    target_id = None
    target_name = None
    target_username = None

    if message.forward_from:
        target_id = message.forward_from.id
        target_name = message.forward_from.full_name
        target_username = message.forward_from.username
    elif message.text and message.text.strip().isdigit():
        target_id = int(message.text.strip())
    else:
        await message.answer(
            "Tushunmadim. Telegram ID (faqat raqam) yuboring yoki xabarni forward qiling."
        )
        return

    await db.add_admin(target_id, target_name, target_username, added_by=message.from_user.id)
    await message.answer(f"✅ {target_name or target_id} admin sifatida qo'shildi.")
    try:
        await message.bot.send_message(
            target_id,
            "Tabriklaymiz! Siz Jony Academy botida <b>admin</b> etib tayinlandingiz.\n"
            "Endi /start bosib admin panelidan foydalanishingiz mumkin.",
        )
    except Exception:
        pass


@router.message(Command("remove_admin"))
async def remove_admin_cmd(message: Message):
    if not await _require_admin(message):
        return
    parts = message.text.split()
    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer("Foydalanish: /remove_admin <telegram_id>")
        return
    target_id = int(parts[1])
    await db.remove_admin(target_id)
    await message.answer(f"✅ {target_id} adminlikdan olib tashlandi.")


@router.message(Command("admins"))
async def list_admins_cmd(message: Message):
    if not await _require_admin(message):
        return
    await _send_admins(message.answer)


@router.callback_query(F.data == "admin_admins")
async def list_admins_cb(callback: CallbackQuery):
    if not await db.is_admin(callback.from_user.id):
        await callback.answer("Bu tugma faqat adminlar uchun.", show_alert=True)
        return
    await _send_admins(callback.message.answer)
    await callback.answer()


@router.message(Command("pending"))
async def pending_examiners_cmd(message: Message):
    if not await _require_admin(message):
        return
    await _send_pending(message.answer)


@router.callback_query(F.data == "admin_pending")
async def pending_examiners_cb(callback: CallbackQuery):
    if not await db.is_admin(callback.from_user.id):
        await callback.answer("Bu tugma faqat adminlar uchun.", show_alert=True)
        return
    await _send_pending(callback.message.answer)
    await callback.answer()


@router.message(Command("bookings"))
async def bookings_overview_cmd(message: Message):
    if not await _require_admin(message):
        return
    await _send_bookings(message.answer)


@router.callback_query(F.data == "admin_bookings")
async def bookings_overview_cb(callback: CallbackQuery):
    if not await db.is_admin(callback.from_user.id):
        await callback.answer("Bu tugma faqat adminlar uchun.", show_alert=True)
        return
    await _send_bookings(callback.message.answer)
    await callback.answer()


@router.message(Command("staff"))
async def staff_list_cmd(message: Message):
    if not await _require_admin(message):
        return
    await _send_staff(message.answer)


@router.callback_query(F.data == "admin_staff")
async def staff_list_cb(callback: CallbackQuery):
    if not await db.is_admin(callback.from_user.id):
        await callback.answer("Bu tugma faqat adminlar uchun.", show_alert=True)
        return
    await _send_staff(callback.message.answer)
    await callback.answer()


# ---------- FILIALLARNI BOSHQARISH ----------

@router.callback_query(F.data == "admin_branches")
async def branches_list_cb(callback: CallbackQuery):
    if not await db.is_admin(callback.from_user.id):
        await callback.answer("Bu tugma faqat adminlar uchun.", show_alert=True)
        return
    branches = await db.get_branches()
    text = (
        "🏢 <b>Filiallar</b>\n\n"
        + ("\n".join(f"• {b}" for b in branches) if branches else "Hozircha filial yo'q.")
        + "\n\nO'chirish uchun filialni tanlang yoki yangi filial qo'shing:"
    )
    await callback.message.answer(text, reply_markup=branch_manage_kb(branches))
    await callback.answer()


@router.callback_query(F.data == "branch_add")
async def branch_add_start(callback: CallbackQuery, state: FSMContext):
    if not await db.is_admin(callback.from_user.id):
        await callback.answer("Bu tugma faqat adminlar uchun.", show_alert=True)
        return
    await state.set_state(AdminStates.branch_add_input)
    await callback.message.answer("Yangi filial nomini kiriting (masalan: Chilonzor):")
    await callback.answer()


@router.message(AdminStates.branch_add_input)
async def branch_add_save(message: Message, state: FSMContext):
    name = message.text.strip()
    if not name:
        await message.answer("Filial nomini kiriting:")
        return
    ok = await db.add_branch(name)
    await state.clear()
    if not ok:
        await message.answer(f"⚠️ \"{name}\" nomli filial allaqachon mavjud.")
        return
    branches = await db.get_branches()
    await message.answer(
        f"✅ \"{name}\" filiali qo'shildi.",
        reply_markup=branch_manage_kb(branches),
    )


@router.callback_query(F.data.startswith("branch_del:"))
async def branch_delete_confirm(callback: CallbackQuery):
    if not await db.is_admin(callback.from_user.id):
        await callback.answer("Bu tugma faqat adminlar uchun.", show_alert=True)
        return
    name = callback.data.split(":", 1)[1]
    await callback.message.answer(
        f"<b>{name}</b> filialini o'chirmoqchimisiz?\n\n"
        "⚠️ Diqqat: bu filial nomi allaqachon ishlatilgan foydalanuvchilar/buyurtmalar "
        "tarixiy yozuvlarida qoladi, faqat yangi tanlov ro'yxatidan olib tashlanadi.",
        reply_markup=branch_delete_confirm_kb(name),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("branch_del_yes:"))
async def branch_delete_yes(callback: CallbackQuery):
    if not await db.is_admin(callback.from_user.id):
        await callback.answer("Bu tugma faqat adminlar uchun.", show_alert=True)
        return
    name = callback.data.split(":", 1)[1]
    await db.remove_branch(name)
    branches = await db.get_branches()
    await callback.message.edit_text(f"✅ \"{name}\" filiali o'chirildi.")
    await callback.message.answer(
        "🏢 <b>Filiallar</b>\n\n"
        + ("\n".join(f"• {b}" for b in branches) if branches else "Hozircha filial yo'q."),
        reply_markup=branch_manage_kb(branches),
    )
    await callback.answer("O'chirildi")


@router.callback_query(F.data == "branch_del_no")
async def branch_delete_no(callback: CallbackQuery):
    await callback.message.edit_text("Bekor qilindi.")
    await callback.answer()


# ---------- TEST TURLARINI BOSHQARISH ----------

@router.callback_query(F.data == "admin_test_types")
async def test_types_list_cb(callback: CallbackQuery):
    if not await db.is_admin(callback.from_user.id):
        await callback.answer("Bu tugma faqat adminlar uchun.", show_alert=True)
        return
    test_types = await db.get_test_types()
    text = (
        "🧪 <b>Test turlari</b>\n\n"
        + ("\n".join(f"• {t}" for t in test_types) if test_types else "Hozircha test turi yo'q.")
        + "\n\nO'chirish uchun test turini tanlang yoki yangisini qo'shing:"
    )
    await callback.message.answer(text, reply_markup=test_type_manage_kb(test_types))
    await callback.answer()


@router.callback_query(F.data == "testtype_add")
async def test_type_add_start(callback: CallbackQuery, state: FSMContext):
    if not await db.is_admin(callback.from_user.id):
        await callback.answer("Bu tugma faqat adminlar uchun.", show_alert=True)
        return
    await state.set_state(AdminStates.testtype_add_input)
    await callback.message.answer("Yangi test turi nomini kiriting (masalan: PLACEMENT TEST):")
    await callback.answer()


@router.message(AdminStates.testtype_add_input)
async def test_type_add_save(message: Message, state: FSMContext):
    name = message.text.strip()
    if not name:
        await message.answer("Test turi nomini kiriting:")
        return
    ok = await db.add_test_type(name)
    await state.clear()
    if not ok:
        await message.answer(f"⚠️ \"{name}\" nomli test turi allaqachon mavjud.")
        return
    test_types = await db.get_test_types()
    await message.answer(
        f"✅ \"{name}\" test turi qo'shildi.",
        reply_markup=test_type_manage_kb(test_types),
    )


@router.callback_query(F.data.startswith("testtype_del:"))
async def test_type_delete_confirm(callback: CallbackQuery):
    if not await db.is_admin(callback.from_user.id):
        await callback.answer("Bu tugma faqat adminlar uchun.", show_alert=True)
        return
    name = callback.data.split(":", 1)[1]
    await callback.message.answer(
        f"<b>{name}</b> test turini o'chirmoqchimisiz?\n\n"
        "⚠️ Diqqat: bu test turi allaqachon ishlatilgan buyurtmalar tarixiy "
        "yozuvlarida qoladi, faqat yangi tanlov ro'yxatidan olib tashlanadi.",
        reply_markup=test_type_delete_confirm_kb(name),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("testtype_del_yes:"))
async def test_type_delete_yes(callback: CallbackQuery):
    if not await db.is_admin(callback.from_user.id):
        await callback.answer("Bu tugma faqat adminlar uchun.", show_alert=True)
        return
    name = callback.data.split(":", 1)[1]
    await db.remove_test_type(name)
    test_types = await db.get_test_types()
    await callback.message.edit_text(f"✅ \"{name}\" test turi o'chirildi.")
    await callback.message.answer(
        "🧪 <b>Test turlari</b>\n\n"
        + ("\n".join(f"• {t}" for t in test_types) if test_types else "Hozircha test turi yo'q."),
        reply_markup=test_type_manage_kb(test_types),
    )
    await callback.answer("O'chirildi")


@router.callback_query(F.data == "testtype_del_no")
async def test_type_delete_no(callback: CallbackQuery):
    await callback.message.edit_text("Bekor qilindi.")
    await callback.answer()


@router.message(Command("daily_report"))
async def daily_report_cmd(message: Message):
    if not await _require_admin(message):
        return
    await _send_daily_report(message.answer)


@router.callback_query(F.data == "admin_daily_report")
async def daily_report_cb(callback: CallbackQuery):
    if not await db.is_admin(callback.from_user.id):
        await callback.answer("Bu tugma faqat adminlar uchun.", show_alert=True)
        return
    await _send_daily_report(callback.message.answer)
    await callback.answer()


def _build_backup_document():
    if not os.path.exists(db.DB_PATH):
        return None, None
    date_str = db.now_tashkent().strftime("%d.%m.%Y %H:%M")
    document = FSInputFile(db.DB_PATH, filename=f"backup_{db.now_tashkent().strftime('%Y%m%d_%H%M')}.db")
    caption = f"🗄 Bazaning zaxira nusxasi — {date_str}"
    return document, caption


@router.message(Command("backup"))
async def backup_cmd(message: Message):
    if not await _require_admin(message):
        return
    document, caption = _build_backup_document()
    if not document:
        await message.answer("Baza fayli topilmadi.")
        return
    await message.answer_document(document, caption=caption)


@router.callback_query(F.data == "admin_backup")
async def backup_cb(callback: CallbackQuery):
    if not await db.is_admin(callback.from_user.id):
        await callback.answer("Bu tugma faqat adminlar uchun.", show_alert=True)
        return
    document, caption = _build_backup_document()
    if not document:
        await callback.answer("Baza fayli topilmadi.", show_alert=True)
        return
    await callback.message.answer_document(document, caption=caption)
    await callback.answer()


@router.message(Command("stats"))
async def stats_cmd(message: Message):
    if not await _require_admin(message):
        return
    await _send_stats(message.answer)


@router.callback_query(F.data == "admin_stats")
async def stats_cb(callback: CallbackQuery):
    if not await db.is_admin(callback.from_user.id):
        await callback.answer("Bu tugma faqat adminlar uchun.", show_alert=True)
        return
    await _send_stats(callback.message.answer)
    await callback.answer()


@router.callback_query(F.data == "admin_search")
async def search_start(callback: CallbackQuery, state: FSMContext):
    if not await db.is_admin(callback.from_user.id):
        await callback.answer("Bu tugma faqat adminlar uchun.", show_alert=True)
        return
    await state.set_state(AdminStates.search_query)
    await callback.message.answer(
        "🔍 Qidiruv so'zini kiriting (ustoz ismi, guruh nomi, filial yoki test turi):"
    )
    await callback.answer()


@router.message(AdminStates.search_query)
async def search_process(message: Message, state: FSMContext):
    await state.clear()
    query = message.text.strip()
    results = await db.search_bookings(query)
    if not results:
        await message.answer(f"\"{query}\" bo'yicha hech narsa topilmadi.")
        return

    status_labels = {
        "pending": "🟡 kutilmoqda",
        "accepted": "🟢 qabul qilingan",
        "cancelled": "🔴 bekor qilingan",
        "expired": "⚪️ muddati o'tgan",
    }
    lines = [f"🔍 <b>\"{query}\" bo'yicha natijalar ({len(results)} ta):</b>\n"]
    for b in results:
        lines.append(
            f"{status_labels.get(b['status'], b['status'])} — {b['exam_date']} {b['exam_time']}\n"
            f"   Filial: {b['branch']}, Ustoz: {b['teacher_name']}\n"
            f"   Guruh: {b['group_name']}, Turi: {b['test_type']}"
        )
    text = "\n\n".join(lines)
    if len(text) > 3500:
        text = text[:3500] + "\n\n... (natijalar ko'p, qidiruvni aniqroq kiriting)"
    await message.answer(text)


@router.callback_query(F.data == "admin_reminder_setting")
async def reminder_setting_start(callback: CallbackQuery, state: FSMContext):
    if not await db.is_admin(callback.from_user.id):
        await callback.answer("Bu tugma faqat adminlar uchun.", show_alert=True)
        return
    current = await db.get_setting("reminder_hours_before") or "1"
    await state.set_state(AdminStates.reminder_input)
    await callback.message.answer(
        f"⏰ Hozirgi sozlama: imtihondan <b>{current}</b> soat oldin eslatma yuboriladi.\n\n"
        "Necha soat oldin eslatma yuborilsin? (masalan: 1 yoki 0.5 yoki 2):"
    )
    await callback.answer()


@router.message(AdminStates.reminder_input)
async def reminder_setting_process(message: Message, state: FSMContext):
    await state.clear()
    try:
        hours = float(message.text.strip().replace(",", "."))
        if hours <= 0:
            raise ValueError
    except ValueError:
        await message.answer("Noto'g'ri qiymat. Faqat musbat son kiriting (masalan: 1 yoki 0.5):")
        return
    await db.set_setting("reminder_hours_before", str(hours))
    await message.answer(f"✅ Endi imtihondan {hours} soat oldin eslatma yuboriladi.")


@router.callback_query(F.data.startswith("remove_staff:"))
async def remove_staff_confirm(callback: CallbackQuery):
    if not await db.is_admin(callback.from_user.id):
        await callback.answer("Bu tugma faqat adminlar uchun.", show_alert=True)
        return
    user_row_id = int(callback.data.split(":")[1])
    user = await db.get_user_by_row_id(user_row_id)
    if not user:
        await callback.answer("Topilmadi.", show_alert=True)
        return

    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Ha, o'chirish", callback_data=f"remove_staff_yes:{user_row_id}")
    builder.button(text="❌ Bekor qilish", callback_data="remove_staff_no")
    builder.adjust(2)
    await callback.message.answer(
        f"<b>{user['full_name']}</b> ni ro'yxatdan o'chirmoqchimisiz?\n"
        "(U keyinchalik /start bosib qayta ro'yxatdan o'ta oladi)",
        reply_markup=builder.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("remove_staff_yes:"))
async def remove_staff_yes(callback: CallbackQuery):
    if not await db.is_admin(callback.from_user.id):
        await callback.answer("Bu tugma faqat adminlar uchun.", show_alert=True)
        return
    user_row_id = int(callback.data.split(":")[1])
    user = await db.get_user_by_row_id(user_row_id)
    await db.deactivate_user_by_row_id(user_row_id)
    await callback.message.edit_text(f"✅ {user['full_name']} ro'yxatdan o'chirildi.")
    try:
        await callback.bot.send_message(
            user["telegram_id"],
            "Sizning hisobingiz admin tomonidan o'chirildi. Savol uchun admin bilan bog'laning.",
        )
    except Exception:
        pass
    await callback.answer("O'chirildi")


@router.callback_query(F.data == "remove_staff_no")
async def remove_staff_no(callback: CallbackQuery):
    await callback.message.edit_text("Bekor qilindi.")
    await callback.answer()


@router.callback_query(F.data.startswith("cancel_booking:"))
async def cancel_booking_confirm(callback: CallbackQuery):
    if not await db.is_admin(callback.from_user.id):
        await callback.answer("Bu tugma faqat adminlar uchun.", show_alert=True)
        return
    booking_id = int(callback.data.split(":")[1])
    booking = await db.get_booking(booking_id)
    if not booking:
        await callback.answer("Topilmadi.", show_alert=True)
        return

    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Ha, bekor qilish", callback_data=f"cancel_booking_yes:{booking_id}")
    builder.button(text="◀️ Yo'q", callback_data="cancel_booking_no")
    builder.adjust(2)
    await callback.message.answer(
        f"<b>{booking['teacher_name']}</b> ning {booking['exam_date']} {booking['exam_time']} "
        f"dagi buyurtmasini bekor qilmoqchimisiz?",
        reply_markup=builder.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("cancel_booking_yes:"))
async def cancel_booking_yes(callback: CallbackQuery):
    if not await db.is_admin(callback.from_user.id):
        await callback.answer("Bu tugma faqat adminlar uchun.", show_alert=True)
        return
    booking_id = int(callback.data.split(":")[1])
    booking = await db.get_booking(booking_id)
    await db.cancel_booking(booking_id)
    await callback.message.edit_text("✅ Buyurtma bekor qilindi.")

    try:
        await callback.bot.send_message(
            booking["teacher_telegram_id"],
            f"❌ Sizning {booking['exam_date']} {booking['exam_time']} dagi imtihon "
            f"buyurtmangiz admin tomonidan bekor qilindi.\n\nSavol uchun admin bilan bog'laning.",
        )
    except Exception:
        pass

    if booking["examiner_telegram_id"]:
        try:
            await callback.bot.send_message(
                booking["examiner_telegram_id"],
                f"❌ {booking['exam_date']} {booking['exam_time']} dagi imtihon "
                f"(ustoz: {booking['teacher_name']}) admin tomonidan bekor qilindi.",
            )
        except Exception:
            pass

    await callback.answer("Bekor qilindi")


@router.callback_query(F.data == "cancel_booking_no")
async def cancel_booking_no(callback: CallbackQuery):
    await callback.message.edit_text("Bekor qilinmadi.")
    await callback.answer()


@router.message(Command("admin"))
async def admin_menu(message: Message):
    if not await _require_admin(message):
        return
    await message.answer("🛠 <b>Admin panel</b>", reply_markup=admin_panel_kb())
