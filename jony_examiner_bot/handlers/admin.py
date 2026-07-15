import asyncio
import os
import sqlite3
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
    grading_thresholds_kb,
    GRADING_LABELS,
    booking_field_manage_kb,
    booking_field_delete_confirm_kb,
    cancel_kb,
    broadcast_confirm_kb,
    broadcast_target_kb,
)

router = Router()


class AddAdminStates(StatesGroup):
    waiting_input = State()


class AddStudyHeadStates(StatesGroup):
    waiting_input = State()


async def _require_admin(message: Message) -> bool:
    if not await db.is_admin(message.from_user.id):
        await message.answer("Bu komanda faqat adminlar uchun.")
        return False
    return True


async def _log_action(from_user, action: str, details: str = None):
    """Qaysi admin nima o'zgartirish qilganini audit logga yozadi.
    from_user — callback.from_user yoki message.from_user (aiogram User)."""
    user = await db.get_user(from_user.id)
    name = (user["full_name"] if user else None) or from_user.full_name or str(from_user.id)
    await db.log_admin_action(from_user.id, name, action, details)


async def _send_audit_log(send):
    actions = await db.get_admin_actions(30)
    if not actions:
        await send("Hozircha hech qanday admin amali qayd etilmagan.")
        return
    lines = ["📜 <b>Adminlar amallari tarixi (oxirgi 30 ta):</b>\n"]
    for a in actions:
        try:
            when = datetime.fromisoformat(a["created_at"]).strftime("%d.%m.%Y %H:%M")
        except ValueError:
            when = a["created_at"]
        line = f"🕒 {when} — <b>{a['admin_name']}</b>: {a['action']}"
        if a.get("details"):
            line += f" ({a['details']})"
        lines.append(line)
    text = "\n".join(lines)
    if len(text) > 3800:
        text = text[:3800] + "\n\n... (davomi bor, ko'proq uchun bazani ko'ring)"
    await send(text)


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

    role_labels = {
        "TEACHER": "👩‍🏫 Ustoz",
        "EXAMINER": "🧑‍💼 Examiner",
        "STUDY_HEAD": "🏫 O'quv bo'lim rahbari",
    }
    status_labels = {
        "active": "", "approved": "", "pending": " (kutilmoqda)", "rejected": " (rad etilgan)",
    }

    by_branch = {}
    study_heads = []
    for s in staff:
        if s["role"] == "STUDY_HEAD":
            study_heads.append(s)
            continue
        branches = await db.get_user_all_branches(s["telegram_id"], s["branch"])
        for br in branches:
            by_branch.setdefault(br, []).append(s)

    for branch, users in by_branch.items():
        lines = [f"📍 <b>{branch}</b>\n"]
        builder = InlineKeyboardBuilder()
        for u in users:
            role_label = role_labels.get(u["role"], u["role"])
            status_label = status_labels.get(u["status"], "")
            lines.append(f"{role_label}: {u['full_name']}{status_label}")
            builder.button(
                text=f"✏️ {u['full_name']} — ismini o'zgartirish",
                callback_data=f"edit_name:{u['telegram_id']}",
            )
            builder.button(
                text=f"❌ {u['full_name']} — shu filialdan chiqarish",
                callback_data=f"remove_staff_branch:{u['telegram_id']}:{branch}",
            )
        builder.adjust(1)
        await send("\n".join(lines), reply_markup=builder.as_markup())

    if study_heads:
        lines = ["📍 <b>O'quv bo'lim rahbarlari</b>\n"]
        builder = InlineKeyboardBuilder()
        for u in study_heads:
            status_label = status_labels.get(u["status"], "")
            lines.append(f"{role_labels['STUDY_HEAD']}: {u['full_name']}{status_label}")
            builder.button(
                text=f"✏️ {u['full_name']} — ismini o'zgartirish",
                callback_data=f"edit_name:{u['telegram_id']}",
            )
            builder.button(text=f"❌ {u['full_name']} (butunlay)", callback_data=f"remove_staff:{u['id']}")
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


async def _send_study_heads(send):
    allowed = await db.list_study_head_allowed()
    if not allowed:
        await send("Hozircha O'quv bo'lim rahbari lavozimi uchun ruxsat berilgan odam yo'q.")
        return
    lines = ["🏫 <b>O'quv bo'lim rahbari — ruxsat berilganlar:</b>\n"]
    for a in allowed:
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
    await _log_action(message.from_user, "Admin guruhni sozladi", str(message.chat.id))
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
    await _log_action(message.from_user, "Admin qo'shdi", f"{target_name or ''} ({target_id})".strip())
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
    await _log_action(message.from_user, "Adminlikdan chiqardi", str(target_id))
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


@router.message(Command("add_study_head"))
async def add_study_head_start(message: Message, state: FSMContext):
    if not await _require_admin(message):
        return
    await state.set_state(AddStudyHeadStates.waiting_input)
    await message.answer(
        "O'quv bo'lim rahbari lavozimini olishga ruxsat berilayotgan odamning "
        "Telegram ID sini yuboring,\nyoki undan (yoki u yuborgan istalgan xabarni) forward qiling."
    )


@router.callback_query(F.data == "admin_add_study_head")
async def add_study_head_start_cb(callback: CallbackQuery, state: FSMContext):
    if not await db.is_admin(callback.from_user.id):
        await callback.answer("Bu tugma faqat adminlar uchun.", show_alert=True)
        return
    await state.set_state(AddStudyHeadStates.waiting_input)
    await callback.message.answer(
        "O'quv bo'lim rahbari lavozimini olishga ruxsat berilayotgan odamning "
        "Telegram ID sini yuboring,\nyoki undan (yoki u yuborgan istalgan xabarni) forward qiling."
    )
    await callback.answer()


@router.message(AddStudyHeadStates.waiting_input)
async def add_study_head_process(message: Message, state: FSMContext):
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

    await db.add_study_head_allowed(target_id, target_name, target_username, added_by=message.from_user.id)
    await _log_action(
        message.from_user, "O'quv bo'lim rahbari ruxsati berdi",
        f"{target_name or ''} ({target_id})".strip(),
    )
    await message.answer(
        f"✅ {target_name or target_id} uchun O'quv bo'lim rahbari lavozimini olish ruxsati berildi."
    )
    try:
        await message.bot.send_message(
            target_id,
            "Sizga <b>O'quv bo'lim rahbari</b> lavozimini olish uchun admin ruxsat berdi.\n"
            "Endi /start (yoki /change_role) bosib, shu lavozimni tanlashingiz mumkin.",
        )
    except Exception:
        pass


@router.message(Command("remove_study_head"))
async def remove_study_head_cmd(message: Message):
    if not await _require_admin(message):
        return
    parts = message.text.split()
    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer("Foydalanish: /remove_study_head <telegram_id>")
        return
    target_id = int(parts[1])
    await db.remove_study_head_allowed(target_id)
    await _log_action(message.from_user, "O'quv bo'lim rahbari ruxsatini olib tashladi", str(target_id))
    await message.answer(f"✅ {target_id} uchun O'quv bo'lim rahbari ruxsati olib tashlandi.")


@router.message(Command("study_heads"))
async def list_study_heads_cmd(message: Message):
    if not await _require_admin(message):
        return
    await _send_study_heads(message.answer)


@router.callback_query(F.data == "admin_study_heads")
async def list_study_heads_cb(callback: CallbackQuery):
    if not await db.is_admin(callback.from_user.id):
        await callback.answer("Bu tugma faqat adminlar uchun.", show_alert=True)
        return
    await _send_study_heads(callback.message.answer)
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


# ---------- O'CHIRILGAN (QORA RO'YXATDAGI) XODIMLARNI TIKLASH ----------

@router.callback_query(F.data == "admin_removed_staff")
async def removed_staff_list_cb(callback: CallbackQuery):
    if not await db.is_admin(callback.from_user.id):
        await callback.answer("Bu tugma faqat adminlar uchun.", show_alert=True)
        return

    removed = await db.get_removed_staff()
    if not removed:
        await callback.message.answer("Hozircha o'chirilgan (qora ro'yxatdagi) xodim yo'q.")
        await callback.answer()
        return

    role_labels = {"TEACHER": "👩‍🏫 Ustoz", "EXAMINER": "🧑‍💼 Examiner", "STUDY_HEAD": "🏫 O'quv bo'lim rahbari"}
    lines = ["🚫 <b>O'chirilgan xodimlar:</b>\n"]
    builder = InlineKeyboardBuilder()
    for u in removed:
        role_label = role_labels.get(u["role"], u["role"])
        lines.append(f"{role_label}: {u['full_name']} — {u['branch']}")
        builder.button(text=f"♻️ {u['full_name']}ni tiklash", callback_data=f"restore_staff:{u['id']}")
    builder.adjust(1)
    await callback.message.answer("\n".join(lines), reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("restore_staff:"))
async def restore_staff(callback: CallbackQuery):
    if not await db.is_admin(callback.from_user.id):
        await callback.answer("Bu tugma faqat adminlar uchun.", show_alert=True)
        return
    user_row_id = int(callback.data.split(":")[1])
    user = await db.get_user_by_row_id(user_row_id)
    if not user:
        await callback.answer("Topilmadi.", show_alert=True)
        return

    await db.reactivate_user_by_row_id(user_row_id)
    await _log_action(callback.from_user, "Xodimni tikladi", user["full_name"])
    await callback.message.edit_text(f"✅ {user['full_name']} tiklandi. Endi /start bosib kira oladi.")
    try:
        await callback.bot.send_message(
            user["telegram_id"],
            "✅ Sizning hisobingiz admin tomonidan tiklandi.\n\nEndi /start bosing.",
        )
    except Exception:
        pass
    await callback.answer("Tiklandi")


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
    await _log_action(message.from_user, "Filial qo'shdi", name)


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
    await _log_action(callback.from_user, "Filialni o'chirdi", name)
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
    await _log_action(message.from_user, "Test turi qo'shdi", name)


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
    await _log_action(callback.from_user, "Test turini o'chirdi", name)
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


# ---------- BAHOLASH CHEGARALARINI BOSHQARISH ----------

@router.callback_query(F.data == "admin_grading")
async def grading_thresholds_cb(callback: CallbackQuery):
    if not await db.is_admin(callback.from_user.id):
        await callback.answer("Bu tugma faqat adminlar uchun.", show_alert=True)
        return
    thresholds = await db.get_grading_thresholds()
    await callback.message.answer(
        "🎯 <b>Baholash chegaralari</b>\n\n"
        "O'zgartirmoqchi bo'lgan chegarani tanlang (foizda, shu qiymatdan boshlab "
        "shu daraja qo'yiladi):",
        reply_markup=grading_thresholds_kb(thresholds),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("grading_edit:"))
async def grading_edit_start(callback: CallbackQuery, state: FSMContext):
    if not await db.is_admin(callback.from_user.id):
        await callback.answer("Bu tugma faqat adminlar uchun.", show_alert=True)
        return
    key = callback.data.split(":", 1)[1]
    if key not in GRADING_LABELS:
        await callback.answer("Noma'lum chegara.", show_alert=True)
        return
    thresholds = await db.get_grading_thresholds()
    await state.set_state(AdminStates.grading_input)
    await state.update_data(grading_key=key)
    await callback.message.answer(
        f"{GRADING_LABELS[key]}\nHozirgi qiymat: <b>{thresholds[key]}%</b>\n\n"
        "Yangi qiymatni foizda kiriting (masalan: 90):"
    )
    await callback.answer()


@router.message(AdminStates.grading_input)
async def grading_edit_save(message: Message, state: FSMContext):
    data = await state.get_data()
    key = data.get("grading_key")
    if key not in GRADING_LABELS:
        await state.clear()
        await message.answer("Xatolik yuz berdi, qaytadan urinib ko'ring.")
        return
    try:
        value = float(message.text.strip().replace(",", "."))
        if not (0 <= value <= 100):
            raise ValueError
    except ValueError:
        await message.answer("Noto'g'ri qiymat. 0 dan 100 gacha son kiriting (masalan: 90):")
        return
    await db.set_grading_threshold(key, value)
    await _log_action(message.from_user, "Baholash chegarasini o'zgartirdi", f"{GRADING_LABELS[key]} → {value}%")
    await state.clear()
    thresholds = await db.get_grading_thresholds()
    await message.answer(
        f"✅ {GRADING_LABELS[key]} endi: <b>{value}%</b>",
        reply_markup=grading_thresholds_kb(thresholds),
    )


# ---------- BUYURTMA QO'SHIMCHA MAYDONLARINI BOSHQARISH ----------

@router.callback_query(F.data == "admin_booking_fields")
async def booking_fields_list_cb(callback: CallbackQuery):
    if not await db.is_admin(callback.from_user.id):
        await callback.answer("Bu tugma faqat adminlar uchun.", show_alert=True)
        return
    fields = await db.get_booking_fields()
    text = (
        "📝 <b>Buyurtma maydonlari</b>\n\n"
        + ("\n".join(f"• {f['label']}" for f in fields) if fields else "Hozircha qo'shimcha maydon yo'q.")
        + "\n\nBular — ustoz imtihon buyurtma qilayotganda standart maydonlardan (filial, "
        "sana, vaqt, test turi, guruh, o'quvchilar soni) tashqari qo'shimcha so'raladigan "
        "maydonlar.\n\nO'chirish uchun tanlang yoki yangisini qo'shing:"
    )
    await callback.message.answer(text, reply_markup=booking_field_manage_kb(fields))
    await callback.answer()


@router.callback_query(F.data == "bookfield_add")
async def booking_field_add_start(callback: CallbackQuery, state: FSMContext):
    if not await db.is_admin(callback.from_user.id):
        await callback.answer("Bu tugma faqat adminlar uchun.", show_alert=True)
        return
    await state.set_state(AdminStates.booking_field_add_input)
    await callback.message.answer(
        "Yangi maydon nomini kiriting (masalan: Sinf raqami, Telefon raqami):"
    )
    await callback.answer()


@router.message(AdminStates.booking_field_add_input)
async def booking_field_add_save(message: Message, state: FSMContext):
    label = message.text.strip()
    if not label:
        await message.answer("Maydon nomini kiriting:")
        return
    ok = await db.add_booking_field(label)
    await state.clear()
    if not ok:
        await message.answer(f"⚠️ \"{label}\" nomli maydon allaqachon mavjud.")
        return
    fields = await db.get_booking_fields()
    await message.answer(
        f"✅ \"{label}\" maydoni qo'shildi. Endi ustozlar buyurtma berayotganda shu maydon ham so'raladi.",
        reply_markup=booking_field_manage_kb(fields),
    )
    await _log_action(message.from_user, "Buyurtma maydonini qo'shdi", label)


@router.callback_query(F.data.startswith("bookfield_del:"))
async def booking_field_delete_confirm(callback: CallbackQuery):
    if not await db.is_admin(callback.from_user.id):
        await callback.answer("Bu tugma faqat adminlar uchun.", show_alert=True)
        return
    field_key = callback.data.split(":", 1)[1]
    fields = {f["field_key"]: f["label"] for f in await db.get_booking_fields()}
    label = fields.get(field_key, field_key)
    await callback.message.answer(
        f"<b>{label}</b> maydonini o'chirmoqchimisiz?\n\n"
        "⚠️ Diqqat: bu maydon bo'yicha eski buyurtmalarda kiritilgan javoblar tarixiy "
        "yozuvlarda qoladi, faqat yangi buyurtmalarda endi so'ralmaydi.",
        reply_markup=booking_field_delete_confirm_kb(field_key),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("bookfield_del_yes:"))
async def booking_field_delete_yes(callback: CallbackQuery):
    if not await db.is_admin(callback.from_user.id):
        await callback.answer("Bu tugma faqat adminlar uchun.", show_alert=True)
        return
    field_key = callback.data.split(":", 1)[1]
    fields_before = {f["field_key"]: f["label"] for f in await db.get_booking_fields()}
    label = fields_before.get(field_key, field_key)
    await db.remove_booking_field(field_key)
    await _log_action(callback.from_user, "Buyurtma maydonini o'chirdi", label)
    fields = await db.get_booking_fields()
    await callback.message.edit_text("✅ Maydon o'chirildi.")
    await callback.message.answer(
        "📝 <b>Buyurtma maydonlari</b>\n\n"
        + ("\n".join(f"• {f['label']}" for f in fields) if fields else "Hozircha qo'shimcha maydon yo'q."),
        reply_markup=booking_field_manage_kb(fields),
    )
    await callback.answer("O'chirildi")


@router.callback_query(F.data == "bookfield_del_no")
async def booking_field_delete_no(callback: CallbackQuery):
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


# ---------- BAZANI FAYLDAN TIKLASH ----------

@router.callback_query(F.data == "admin_restore_db")
async def restore_db_start(callback: CallbackQuery, state: FSMContext):
    if not await db.is_admin(callback.from_user.id):
        await callback.answer("Bu tugma faqat adminlar uchun.", show_alert=True)
        return
    await state.set_state(AdminStates.restore_db_upload)
    await callback.message.answer(
        "⚠️ <b>Diqqat!</b> Yuboradigan .db fayl HOZIRGI bazani TO'LIQ almashtiradi "
        "(barcha odamlar, buyurtmalar, sozlamalar shu fayldagisi bilan almashadi).\n\n"
        "Tiklamoqchi bo'lgan .db faylni (masalan, avval \"📥 Bazani hoziroq yuklab olish\" "
        "orqali olingan faylni) shu yerga yuboring:",
        reply_markup=cancel_kb(),
    )
    await callback.answer()


@router.message(AdminStates.restore_db_upload, F.text == "❌ Bekor qilish")
async def restore_db_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Bekor qilindi. Baza o'zgarmadi.")


@router.message(AdminStates.restore_db_upload, F.document)
async def restore_db_process(message: Message, state: FSMContext):
    doc = message.document
    if not (doc.file_name or "").lower().endswith(".db"):
        await message.answer("Iltimos, .db kengaytmali fayl yuboring (yoki \"❌ Bekor qilish\"):")
        return

    # MUHIM: vaqtinchalik faylni DB_PATH bilan BIR XIL papkaga (bir xil disk/Volume)
    # yozamiz — shundagina pastdagi os.replace() atomik (bitta rename amali) bo'ladi.
    # Agar /tmp kabi boshqa fayl tizimiga yozib, keyin nusxalasak (shutil.copyfile),
    # nusxalash bo'lak-bo'lak ketadi: aynan shu daqiqada boshqa filialdan kelgan
    # buyurtma botni bazaga yozayotgan bo'lsa, u yarim yozilgan (buzilgan) faylni
    # o'qib/yozib qolishi mumkin edi. os.replace() esa POSIX'da bitta atomik
    # operatsiya — hech qachon "yarim holat" bo'lmaydi.
    tmp_path = f"{db.DB_PATH}.restore_tmp_{message.from_user.id}"
    file = await message.bot.get_file(doc.file_id)
    await message.bot.download_file(file.file_path, tmp_path)

    # Fayl haqiqiy va buzilmagan SQLite baza ekanligini tekshiramiz
    try:
        with open(tmp_path, "rb") as f:
            header = f.read(16)
        if not header.startswith(b"SQLite format 3"):
            raise ValueError("SQLite fayl emas")
        check_conn = sqlite3.connect(tmp_path)
        check_conn.execute("SELECT COUNT(*) FROM users")
        check_conn.close()
    except Exception:
        await state.clear()
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        await message.answer(
            "⚠️ Bu fayl to'g'ri baza fayli emas (yoki buzilgan). Tiklash bekor qilindi, "
            "hozirgi baza o'zgarmadi."
        )
        return

    os.replace(tmp_path, db.DB_PATH)

    # MUHIM: tiklangan fayl ESKI (masalan, yangi jadvallar qo'shilishidan oldingi)
    # backup bo'lishi mumkin. init_db() qayta chaqirilsa, yetishmayotgan jadvallar
    # ("CREATE TABLE IF NOT EXISTS" orqali) shu faylda avtomatik yaratiladi —
    # botni qayta ishga tushirmasdan ham sxema yangilanadi.
    await db.init_db()

    await state.clear()
    await _log_action(message.from_user, "Bazani fayldan tikladi (TO'LIQ almashtirdi)")
    await message.answer(
        "✅ Baza muvaffaqiyatli tiklandi! Bot shu fayldagi ma'lumotlar bilan davom etadi.\n\n"
        "ℹ️ Agar Railway'da hali doimiy Volume ulanmagan bo'lsa, keyingi safar kod "
        "yangilanganda baza yana noldan boshlanishi mumkin — buni butunlay hal qilish "
        "uchun Volume ulash tavsiya etiladi."
    )


@router.message(AdminStates.restore_db_upload)
async def restore_db_wrong_input(message: Message):
    await message.answer(
        "Iltimos, .db faylni biriktirib yuboring, yoki \"❌ Bekor qilish\" deb bosing."
    )


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
    await _log_action(message.from_user, "Eslatma vaqtini o'zgartirdi", f"{hours} soat oldin")
    await message.answer(f"✅ Endi imtihondan {hours} soat oldin eslatma yuboriladi.")


# =========================================================
# XODIM ISMINI O'ZGARTIRISH
# =========================================================

@router.callback_query(F.data.startswith("edit_name:"))
async def edit_name_start(callback: CallbackQuery, state: FSMContext):
    if not await db.is_admin(callback.from_user.id):
        await callback.answer("Bu tugma faqat adminlar uchun.", show_alert=True)
        return

    telegram_id = int(callback.data.split(":", 1)[1])
    user = await db.get_user(telegram_id)
    if not user:
        await callback.answer("Bu foydalanuvchi topilmadi (o'chirilgan bo'lishi mumkin).", show_alert=True)
        return

    await state.update_data(edit_name_telegram_id=telegram_id, edit_name_old=user["full_name"])
    await state.set_state(AdminStates.edit_name_input)
    await callback.message.answer(
        f"Joriy ism: <b>{user['full_name']}</b>\n\nYangi to'liq ismni kiriting:"
    )
    await callback.answer()


@router.message(AdminStates.edit_name_input)
async def edit_name_save(message: Message, state: FSMContext):
    new_name = message.text.strip()
    if not new_name:
        await message.answer("Ism bo'sh bo'lmasligi kerak. Qaytadan kiriting:")
        return

    data = await state.get_data()
    telegram_id = data.get("edit_name_telegram_id")
    old_name = data.get("edit_name_old")
    await state.clear()

    user = await db.get_user(telegram_id)
    if not user:
        await message.answer("Bu foydalanuvchi topilmadi (o'chirilgan bo'lishi mumkin).")
        return

    await db.update_user_name(telegram_id, new_name)
    await _log_action(message.from_user, "Xodim ismini o'zgartirdi", f"{old_name} → {new_name}")
    await message.answer(
        f"✅ Ism o'zgartirildi: {old_name} → <b>{new_name}</b>",
        reply_markup=admin_panel_kb(),
    )

    try:
        await message.bot.send_message(
            telegram_id,
            f"ℹ️ Sizning ismingiz admin tomonidan o'zgartirildi: <b>{new_name}</b>",
        )
    except Exception:
        pass


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
    await _log_action(callback.from_user, "Xodimni butunlay o'chirdi", user["full_name"])
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


# ---------- XODIMNI FAQAT BITTA FILIALDAN CHIQARISH ----------

@router.callback_query(F.data.startswith("remove_staff_branch:"))
async def remove_staff_branch_confirm(callback: CallbackQuery):
    if not await db.is_admin(callback.from_user.id):
        await callback.answer("Bu tugma faqat adminlar uchun.", show_alert=True)
        return
    _, telegram_id_str, branch = callback.data.split(":", 2)
    telegram_id = int(telegram_id_str)
    user = await db.get_user(telegram_id)
    if not user:
        await callback.answer("Foydalanuvchi topilmadi.", show_alert=True)
        return

    branches = await db.get_user_all_branches(telegram_id, user["branch"])
    warn = ""
    if len(branches) <= 1:
        warn = "\n\n⚠️ Bu uning YAGONA filiali — chiqarilsa, hisobi butunlay o'chiriladi."

    builder = InlineKeyboardBuilder()
    builder.button(
        text="✅ Ha, chiqarish", callback_data=f"remove_staff_branch_yes:{telegram_id}:{branch}"
    )
    builder.button(text="❌ Bekor qilish", callback_data="remove_staff_no")
    builder.adjust(2)
    await callback.message.answer(
        f"<b>{user['full_name']}</b>ni <b>{branch}</b> filialidan chiqarmoqchimisiz?{warn}",
        reply_markup=builder.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("remove_staff_branch_yes:"))
async def remove_staff_branch_yes(callback: CallbackQuery):
    if not await db.is_admin(callback.from_user.id):
        await callback.answer("Bu tugma faqat adminlar uchun.", show_alert=True)
        return
    _, telegram_id_str, branch = callback.data.split(":", 2)
    telegram_id = int(telegram_id_str)
    user = await db.get_user(telegram_id)
    if not user:
        await callback.answer("Topilmadi.", show_alert=True)
        return

    await db.remove_user_from_branch(telegram_id, branch)
    await _log_action(callback.from_user, "Xodimni filialdan chiqardi", f"{user['full_name']} — {branch}")
    await callback.message.edit_text(f"✅ {user['full_name']} — {branch} filialidan chiqarildi.")

    try:
        after = await db.get_user(telegram_id)
        if after and after["status"] == "removed":
            await callback.bot.send_message(
                telegram_id,
                f"Sizning hisobingiz admin tomonidan o'chirildi ({branch} — yagona filialingiz edi). "
                "Savol uchun admin bilan bog'laning.",
            )
        else:
            await callback.bot.send_message(
                telegram_id,
                f"ℹ️ Siz admin tomonidan <b>{branch}</b> filialidan chiqarildingiz.",
            )
    except Exception:
        pass

    await callback.answer("Bajarildi")


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
    await _log_action(
        callback.from_user, "Buyurtmani bekor qildi",
        f"{booking['teacher_name']} — {booking['exam_date']} {booking['exam_time']}",
    )
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


@router.callback_query(F.data == "admin_audit_log")
async def audit_log_cb(callback: CallbackQuery):
    if not await db.is_admin(callback.from_user.id):
        await callback.answer("Bu tugma faqat adminlar uchun.", show_alert=True)
        return
    await _send_audit_log(callback.message.answer)
    await callback.answer()


@router.message(Command("audit_log"))
async def audit_log_cmd(message: Message):
    if not await _require_admin(message):
        return
    await _send_audit_log(message.answer)


# ---------- BARCHAGA XABAR YUBORISH (BROADCAST) ----------

BROADCAST_TARGET_LABELS = {
    "EXAMINER": "🧑‍💼 Faqat examinerlarga",
    "TEACHER": "👩‍🏫 Faqat ustozlarga",
    "ALL": "📢 Hammaga (barcha ustoz, examiner va adminlarga)",
}


async def _broadcast_target_ids(target: str) -> list:
    if target == "EXAMINER":
        return await db.get_user_ids_by_role("EXAMINER")
    if target == "TEACHER":
        return await db.get_user_ids_by_role("TEACHER")
    return await db.get_all_user_ids()


@router.callback_query(F.data == "admin_broadcast")
async def broadcast_start(callback: CallbackQuery, state: FSMContext):
    if not await db.is_admin(callback.from_user.id):
        await callback.answer("Bu tugma faqat adminlar uchun.", show_alert=True)
        return
    await state.set_state(AdminStates.broadcast_target)
    await callback.message.edit_text(
        "📢 Xabarni kimlarga yubormoqchisiz?",
        reply_markup=broadcast_target_kb(),
    )
    await callback.answer()


@router.callback_query(AdminStates.broadcast_target, F.data == "broadcast_target_cancel")
async def broadcast_target_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Bekor qilindi.")
    await callback.message.answer("🛠 Admin panel", reply_markup=admin_panel_kb())
    await callback.answer()


@router.callback_query(AdminStates.broadcast_target, F.data.startswith("broadcast_target:"))
async def broadcast_target_pick(callback: CallbackQuery, state: FSMContext):
    target = callback.data.split(":", 1)[1]
    if target not in BROADCAST_TARGET_LABELS:
        await callback.answer("Noto'g'ri tanlov.", show_alert=True)
        return
    await state.update_data(broadcast_target=target)
    await state.set_state(AdminStates.broadcast_input)
    await callback.message.edit_text(f"Tanlandi: {BROADCAST_TARGET_LABELS[target]} ✅")
    await callback.message.answer(
        "Xabar matnini kiriting:",
        reply_markup=cancel_kb(),
    )
    await callback.answer()


@router.message(AdminStates.broadcast_input, F.text == "❌ Bekor qilish")
async def broadcast_input_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Bekor qilindi.", reply_markup=admin_panel_kb())


@router.message(AdminStates.broadcast_input)
async def broadcast_input_save(message: Message, state: FSMContext):
    text = message.text
    if not text or not text.strip():
        await message.answer("Iltimos, matn kiriting (yoki \"❌ Bekor qilish\"):")
        return

    data = await state.get_data()
    target = data.get("broadcast_target", "ALL")
    user_ids = await _broadcast_target_ids(target)
    await state.update_data(broadcast_text=text)
    await state.set_state(AdminStates.broadcast_confirm)
    await message.answer(
        f"📢 <b>{BROADCAST_TARGET_LABELS[target]}</b>\n"
        f"Quyidagi xabar taxminan {len(user_ids)} kishiga yuboriladi:\n\n"
        f"—————————————\n{text}\n—————————————\n\n"
        "Yuborishni tasdiqlaysizmi?",
        reply_markup=broadcast_confirm_kb(),
    )


@router.callback_query(AdminStates.broadcast_confirm, F.data == "broadcast_cancel")
async def broadcast_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Bekor qilindi. Xabar yuborilmadi.")
    await callback.message.answer("🛠 Admin panel", reply_markup=admin_panel_kb())
    await callback.answer()


async def _run_broadcast(bot, admin_chat_id: int, text: str, target: str = "ALL"):
    """Fon vazifasi sifatida — Telegram flood-limitiga tushmaslik uchun har
    xabar orasida kichik pauza bilan, hammaga birma-bir yuboradi. Tugagach,
    adminga qisqacha natija xabarini yuboradi."""
    user_ids = await _broadcast_target_ids(target)
    sent, failed = 0, 0
    for telegram_id in user_ids:
        try:
            await bot.send_message(telegram_id, text)
            sent += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.05)

    try:
        await bot.send_message(
            admin_chat_id,
            f"✅ Xabar yuborish yakunlandi ({BROADCAST_TARGET_LABELS.get(target, target)}).\n"
            f"Muvaffaqiyatli: {sent} ta\nYuborilmadi: {failed} ta",
        )
    except Exception:
        pass


@router.callback_query(AdminStates.broadcast_confirm, F.data == "broadcast_send")
async def broadcast_send(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    text = data.get("broadcast_text")
    target = data.get("broadcast_target", "ALL")
    await state.clear()

    if not text:
        await callback.message.edit_text("Xatolik yuz berdi, xabar topilmadi. Qaytadan urinib ko'ring.")
        await callback.answer()
        return

    await callback.message.edit_text("📤 Xabar yuborilmoqda... Tugagach sizga natija yoziladi.")
    await _log_action(callback.from_user, "Xabar yubordi", f"[{target}] {text[:200]}")
    asyncio.create_task(_run_broadcast(callback.bot, callback.from_user.id, text, target))
    await callback.answer()


@router.message(Command("admin"))
async def admin_menu(message: Message):
    if not await _require_admin(message):
        return
    await message.answer("🛠 <b>Admin panel</b>", reply_markup=admin_panel_kb())
