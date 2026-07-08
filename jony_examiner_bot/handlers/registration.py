from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

import database as db
from states import RegStates
from keyboards import (
    role_choice_kb,
    admin_panel_kb,
    branch_kb,
    teacher_menu_kb,
    examiner_menu_kb,
    examiner_approve_kb,
)

router = Router()


async def send_menu_for_user(message: Message, user: dict):
    if user["role"] == "TEACHER":
        await message.answer(
            f"Xush kelibsiz, {user['full_name']}! ({user['branch']} filiali)\n\n"
            "Imtihon buyurtma qilish uchun tugmani bosing:\n\n"
            "(Rolni o'zgartirish kerak bo'lsa: /change_role)",
            reply_markup=teacher_menu_kb(),
        )
    elif user["role"] == "EXAMINER":
        if user["status"] == "pending":
            await message.answer(
                "So'rovingiz hali admin tomonidan tasdiqlanmagan. Iltimos, kuting."
            )
        elif user["status"] == "rejected":
            await message.answer("Afsuski, so'rovingiz rad etilgan. Admin bilan bog'laning.")
        else:
            await message.answer(
                f"Xush kelibsiz, {user['full_name']}! ({user['branch']} filiali, Examiner)\n\n"
                "Test natijalarini kiritish uchun tugmani bosing. Sizga mos filialdagi "
                "yangi imtihon buyurtmalari haqida ham shu yerda xabar beriladi.\n\n"
                "(Rolni o'zgartirish kerak bo'lsa: /change_role)",
                reply_markup=examiner_menu_kb(),
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
            "Admin komandalari uchun /admin yozing.\n\n"
            "Agar bundan tashqari Ustoz yoki Examiner sifatida ham ro'yxatdan "
            "o'tmoqchi bo'lsangiz, quyidagidan tanlang (ixtiyoriy):",
            reply_markup=role_choice_kb(show_admin=True),
        )
        await state.set_state(RegStates.choose_role)
        return

    await state.set_state(RegStates.choose_role)
    await message.answer(
        "Assalomu alaykum! 👋\n<b>Jony Academy Bot</b>ga xush kelibsiz.\n\n"
        "Avval ro'yxatdan o'tamiz. Siz kimsiz?",
        reply_markup=role_choice_kb(),
    )


@router.callback_query(RegStates.choose_role, F.data.startswith("role:"))
async def choose_role(callback: CallbackQuery, state: FSMContext):
    role = callback.data.split(":")[1]

    if role == "ADMIN":
        if not await db.is_admin(callback.from_user.id):
            await callback.answer("Admin rolini faqat mavjud admin tanlay oladi.", show_alert=True)
            return
        await state.clear()
        await callback.message.edit_text(
            "🛠 <b>Admin panel</b>\n\nKerakli bo'limni tanlang:",
            reply_markup=admin_panel_kb(),
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

    status = "active" if role == "TEACHER" else "pending"
    await db.upsert_user(telegram_id, role, full_name, branch, status, username)
    await state.clear()

    if role == "TEACHER":
        await callback.message.edit_text(f"Ro'yxatdan o'tdingiz ✅\nFilial: {branch}")
        await callback.message.answer(
            "Imtihon buyurtma qilish uchun tugmani bosing:",
            reply_markup=teacher_menu_kb(),
        )
    else:
        await callback.message.edit_text(
            "So'rovingiz yuborildi ✅\nAdmin tasdiqlashini kuting."
        )
        admin_group_id = await db.get_setting("admin_group_id")
        if admin_group_id:
            uname = f"@{username}" if username else "username yo'q"
            await callback.bot.send_message(
                int(admin_group_id),
                f"🆕 <b>Yangi Examiner so'rovi</b>\n\n"
                f"Ism: {full_name}\nFilial: {branch}\nTelegram: {uname}",
                reply_markup=examiner_approve_kb(telegram_id),
            )
    await callback.answer()


@router.callback_query(F.data.startswith("approve_examiner:"))
async def approve_examiner(callback: CallbackQuery):
    if not await db.is_admin(callback.from_user.id):
        await callback.answer("Bu tugma faqat adminlar uchun.", show_alert=True)
        return
    telegram_id = int(callback.data.split(":")[1])
    await db.update_user_status(telegram_id, "approved")
    user = await db.get_user(telegram_id)
    await callback.message.edit_text(
        callback.message.text + "\n\n✅ TASDIQLANDI"
    )
    try:
        await callback.bot.send_message(
            telegram_id,
            "Tabriklaymiz! So'rovingiz tasdiqlandi ✅\n\n"
            "Endi test natijalarini kiritish uchun /start bosing.",
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
    await callback.message.edit_text(
        callback.message.text + "\n\n❌ RAD ETILDI"
    )
    try:
        await callback.bot.send_message(
            telegram_id, "Afsuski, so'rovingiz rad etildi. Admin bilan bog'laning."
        )
    except Exception:
        pass
    await callback.answer("Rad etildi")


@router.message(Command("change_role"))
async def change_role(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(RegStates.choose_role)
    await message.answer(
        "Rolingizni qayta tanlang (mavjud ma'lumotlaringiz yangilanadi):",
        reply_markup=role_choice_kb(show_admin=await db.is_admin(message.from_user.id)),
    )


@router.message(Command("whoami"))
async def whoami(message: Message):
    user = await db.get_user(message.from_user.id)
    is_adm = await db.is_admin(message.from_user.id)
    if not user and not is_adm:
        await message.answer("Siz hali ro'yxatdan o'tmagansiz. /start bosing.")
        return
    lines = []
    if user:
        lines.append(
            f"Ism: {user['full_name']}\nRol: {user['role']}\n"
            f"Filial: {user['branch']}\nHolat: {user['status']}"
        )
    if is_adm:
        lines.append("🛠 Siz ADMIN sifatida ham belgilangansiz.")
    await message.answer("\n\n".join(lines))
