from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

import database as db
from states import RegStates
from keyboards import (
    role_choice_kb,
    branch_kb,
    build_main_menu_kb,
    admin_only_menu_kb,
    admin_panel_kb,
)

router = Router()


async def send_menu_for_user(message: Message, user: dict):
    is_adm = await db.is_admin(message.from_user.id)
    if user["role"] == "TEACHER":
        await message.answer(
            f"Xush kelibsiz, {user['full_name']}! ({user['branch']} filiali)\n\n"
            "Imtihon buyurtma qilish uchun tugmani bosing.\n"
            "(Rolni o'zgartirish: /change_role)",
            reply_markup=build_main_menu_kb("TEACHER", is_adm),
        )
    elif user["role"] == "EXAMINER":
        if user["status"] == "rejected":
            await message.answer("Afsuski, so'rovingiz rad etilgan. Admin bilan bog'laning.")
            return
        await message.answer(
            f"Xush kelibsiz, {user['full_name']}! ({user['branch']} filiali, Examiner)\n\n"
            "Test natijalarini kiritish uchun tugmani bosing. Sizga mos filialdagi "
            "yangi imtihon buyurtmalari haqida ham shu yerda xabar beriladi.\n"
            "(Rolni o'zgartirish: /change_role)",
            reply_markup=build_main_menu_kb("EXAMINER", is_adm),
        )


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user = await db.get_user(message.from_user.id)
    if user:
        if user["status"] == "removed":
            await message.answer(
                "Sizning hisobingiz admin tomonidan o'chirilgan. Savol uchun admin bilan bog'laning."
            )
            return
        await send_menu_for_user(message, user)
        return

    is_adm = await db.is_admin(message.from_user.id)
    if is_adm:
        await message.answer(
            "👋 Siz <b>ADMIN</b> sifatida belgilangansiz!\n\n"
            "Pastdagi tugma orqali admin panelga kirishingiz mumkin.\n\n"
            "Agar bundan tashqari Ustoz yoki Examiner sifatida ham ro'yxatdan "
            "o'tmoqchi bo'lsangiz, /change_role yozing.",
            reply_markup=admin_only_menu_kb(),
        )
        return

    await state.set_state(RegStates.choose_role)
    await message.answer(
        "Assalomu alaykum! 👋\n<b>Jony Academy Bot</b>ga xush kelibsiz.\n\n"
        "Avval ro'yxatdan o'tamiz. Siz kimsiz?",
        reply_markup=role_choice_kb(),
    )


@router.message(Command("change_role"))
async def change_role(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(RegStates.choose_role)
    await message.answer(
        "Rolingizni tanlang:",
        reply_markup=role_choice_kb(),
    )


@router.message(F.text == "🛠 Admin panel")
async def admin_panel_button(message: Message):
    if not await db.is_admin(message.from_user.id):
        await message.answer("Siz admin emassiz.")
        return
    await message.answer("🛠 <b>Admin panel</b>", reply_markup=admin_panel_kb())


@router.callback_query(RegStates.choose_role, F.data.startswith("role:"))
async def choose_role(callback: CallbackQuery, state: FSMContext):
    role = callback.data.split(":")[1]

    if role == "ADMIN":
        await state.clear()
        is_adm = await db.is_admin(callback.from_user.id)
        if is_adm:
            await callback.message.edit_text("🛠 Siz admin ekansiz.")
            await callback.message.answer("Admin panel:", reply_markup=admin_panel_kb())
        else:
            await callback.message.edit_text(
                "Siz hali admin emassiz. Admin bo'lish uchun mavjud admin sizni "
                "/add_admin orqali qo'shishi kerak."
            )
        await callback.answer()
        return

    await state.update_data(role=role)
    await state.set_state(RegStates.full_name)
    await callback.message.edit_text("Ism va familiyangizni kiriting:")
    await callback.answer()


@router.message(RegStates.full_name)
async def get_full_name(message: Message, state: FSMContext):
    await state.update_data(full_name=message.text)
    await state.set_state(RegStates.choose_branch)
    await message.answer("Filialingizni tanlang:", reply_markup=branch_kb())


@router.callback_query(RegStates.choose_branch, F.data.startswith("branch:"))
async def choose_branch(callback: CallbackQuery, state: FSMContext):
    branch = callback.data.split(":")[1]
    data = await state.get_data()
    role = data["role"]
    full_name = data["full_name"]
    telegram_id = callback.from_user.id
    username = callback.from_user.username

    # Endi ustoz ham, examiner ham darhol faol bo'ladi — admin tasdiqlash shart emas
    status = "active"
    await db.upsert_user(telegram_id, role, full_name, branch, status, username)
    if role == "TEACHER":
        await db.add_teacher_branch(telegram_id, branch)
    await state.clear()

    is_adm = await db.is_admin(telegram_id)

    if role == "TEACHER":
        await callback.message.edit_text(f"Ro'yxatdan o'tdingiz ✅\nFilial: {branch}")
        await callback.message.answer(
            "Imtihon buyurtma qilish uchun tugmani bosing:",
            reply_markup=build_main_menu_kb("TEACHER", is_adm),
        )
    else:
        await callback.message.edit_text(f"Ro'yxatdan o'tdingiz ✅\nFilial: {branch}")
        await callback.message.answer(
            "Test natijalarini kiritish uchun tugmani bosing:",
            reply_markup=build_main_menu_kb("EXAMINER", is_adm),
        )
        admin_group_id = await db.get_setting("admin_group_id")
        if admin_group_id:
            uname = f"@{username}" if username else "username yo'q"
            try:
                await callback.bot.send_message(
                    int(admin_group_id),
                    f"ℹ️ Yangi Examiner ro'yxatdan o'tdi\n\n"
                    f"Ism: {full_name}\nFilial: {branch}\nTelegram: {uname}",
                )
            except Exception:
                pass
    await callback.answer()


# ---------- FILIAL QO'SHISH (ustoz bir nechta filialda ishlashi uchun) ----------

@router.message(F.text == "➕ Filial qo'shish")
async def add_branch_start(message: Message):
    user = await db.get_user(message.from_user.id)
    if not user or user["role"] != "TEACHER":
        return
    existing = await db.get_teacher_branches(message.from_user.id)
    from keyboards import BRANCHES
    if len(existing) >= len(BRANCHES):
        await message.answer("Siz allaqachon barcha filiallarga qo'shilgansiz.")
        return
    await message.answer(
        "Qaysi filialni qo'shmoqchisiz?",
        reply_markup=branch_kb(prefix="addbranch", exclude=existing),
    )


@router.callback_query(F.data.startswith("addbranch:"))
async def add_branch_confirm(callback: CallbackQuery):
    branch = callback.data.split(":", 1)[1]
    await db.add_teacher_branch(callback.from_user.id, branch)
    await callback.message.edit_text(f"✅ {branch} filiali qo'shildi.")
    await callback.answer()


# ---------- ADMIN PANEL TUGMALARI (callback) ----------

@router.callback_query(F.data == "admin_group_info")
async def admin_group_info(callback: CallbackQuery):
    await callback.message.answer(
        "Admin guruhni belgilash uchun:\n"
        "1. Botni kerakli guruhga qo'shing\n"
        "2. O'sha guruhda <code>/admin_group</code> deb yozing\n\n"
        "(Bu faqat guruh ichida ishlaydi, shaxsiy chatda emas)"
    )
    await callback.answer()


# ---------- ESKI (endi ishlatilmaydi, lekin eski pending yozuvlar uchun qoldirilgan) ----------

@router.callback_query(F.data.startswith("approve_examiner:"))
async def approve_examiner(callback: CallbackQuery):
    if not await db.is_admin(callback.from_user.id):
        await callback.answer("Bu tugma faqat adminlar uchun.", show_alert=True)
        return
    telegram_id = int(callback.data.split(":")[1])
    await db.update_user_status(telegram_id, "active")
    try:
        await callback.message.edit_text(callback.message.text + "\n\n✅ TASDIQLANDI")
    except Exception:
        pass
    try:
        await callback.bot.send_message(
            telegram_id,
            "Tabriklaymiz! So'rovingiz tasdiqlandi ✅\n\nEndi /start bosing.",
        )
    except Exception:
        pass
    await callback.answer("Tasdiqlandi")


@router.callback_query(F.data.startswith("reject_examiner:"))
async def reject_examiner(callback: CallbackQuery):
    if not await db.is_admin(callback.from_user.id):
        await callback.answer("Bu tugma faqat adminlar uchun.", show_alert=True)
        return
    telegram_id = int(callback.data.split(":")[1])
    await db.update_user_status(telegram_id, "rejected")
    try:
        await callback.message.edit_text(callback.message.text + "\n\n❌ RAD ETILDI")
    except Exception:
        pass
    try:
        await callback.bot.send_message(
            telegram_id, "Afsuski, so'rovingiz rad etildi. Admin bilan bog'laning."
        )
    except Exception:
        pass
    await callback.answer("Rad etildi")


@router.message(Command("whoami"))
async def whoami(message: Message):
    user = await db.get_user(message.from_user.id)
    is_adm = await db.is_admin(message.from_user.id)
    if not user and not is_adm:
        await message.answer("Siz hali ro'yxatdan o'tmagansiz. /start bosing.")
        return
    lines = []
    if user:
        branches = await db.get_teacher_branches(message.from_user.id) if user["role"] == "TEACHER" else []
        branch_text = f"\nFiliallar: {', '.join(branches)}" if branches else ""
        lines.append(
            f"Ism: {user['full_name']}\nRol: {user['role']}\n"
            f"Filial: {user['branch']}{branch_text}\nHolat: {user['status']}"
        )
    if is_adm:
        lines.append("🛠 Siz ADMIN sifatida ham belgilangansiz.")
    await message.answer("\n\n".join(lines))
