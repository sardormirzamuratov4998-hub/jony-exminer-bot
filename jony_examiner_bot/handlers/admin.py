from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

import database as db
from keyboards import examiner_approve_kb

router = Router()


class AddAdminStates(StatesGroup):
    waiting_input = State()


async def _require_admin(message: Message) -> bool:
    if not await db.is_admin(message.from_user.id):
        await message.answer("Bu komanda faqat adminlar uchun.")
        return False
    return True


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
            "Endi /admin buyrug'i orqali admin panelidan foydalanishingiz mumkin.",
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
    admins = await db.list_admins()
    if not admins:
        await message.answer("Hozircha adminlar yo'q.")
        return
    lines = ["👤 <b>Adminlar ro'yxati:</b>\n"]
    for a in admins:
        name = a["full_name"] or "Noma'lum"
        uname = f"@{a['username']}" if a["username"] else ""
        lines.append(f"• {name} {uname} — ID: {a['telegram_id']}")
    await message.answer("\n".join(lines))


@router.message(Command("pending"))
async def pending_examiners_cmd(message: Message):
    if not await _require_admin(message):
        return
    pending = await db.get_pending_examiners()
    if not pending:
        await message.answer("Kutilayotgan examiner so'rovlari yo'q.")
        return
    for p in pending:
        uname = f"@{p['username']}" if p["username"] else "username yo'q"
        await message.answer(
            f"Ism: {p['full_name']}\nFilial: {p['branch']}\nTelegram: {uname}",
            reply_markup=examiner_approve_kb(p["telegram_id"]),
        )


@router.message(Command("bookings"))
async def bookings_overview_cmd(message: Message):
    if not await _require_admin(message):
        return
    bookings = await db.get_active_bookings()
    if not bookings:
        await message.answer("Faol buyurtmalar yo'q.")
        return
    lines = ["📅 <b>Faol buyurtmalar:</b>\n"]
    for b in bookings:
        status_emoji = "🟡" if b["status"] == "pending" else "🟢"
        examiner = f" — {b['examiner_name']}" if b["examiner_name"] else " — kutilmoqda"
        lines.append(
            f"{status_emoji} {b['exam_date']} {b['exam_time']} | {b['branch']} | "
            f"{b['teacher_name']} | {b['group_name']}{examiner}"
        )
    await message.answer("\n".join(lines))


@router.message(Command("staff"))
async def staff_list_cmd(message: Message):
    if not await _require_admin(message):
        return
    staff = await db.get_all_staff()
    if not staff:
        await message.answer("Hozircha ro'yxatdan o'tgan xodim yo'q.")
        return

    from aiogram.utils.keyboard import InlineKeyboardBuilder

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
            builder.button(
                text=f"❌ {u['full_name']}", callback_data=f"remove_staff:{u['id']}"
            )
        builder.adjust(1)
        await message.answer("\n".join(lines), reply_markup=builder.as_markup())


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

    from aiogram.utils.keyboard import InlineKeyboardBuilder
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


@router.message(Command("admin"))
async def admin_menu(message: Message):
    if not await _require_admin(message):
        return
    await message.answer(
        "🛠 <b>Admin panel</b>\n\n"
        "/pending — kutilayotgan examiner so'rovlari\n"
        "/bookings — faol buyurtmalar ro'yxati\n"
        "/staff — barcha xodimlar ro'yxati (o'chirish imkoni bilan)\n"
        "/admins — adminlar ro'yxati\n"
        "/add_admin — yangi admin qo'shish\n"
        "/remove_admin <id> — adminni olib tashlash\n"
        "/admin_group — shu guruhni admin guruh qilib belgilash"
    )
