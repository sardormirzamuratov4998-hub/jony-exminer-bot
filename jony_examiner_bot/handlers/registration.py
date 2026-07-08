from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

import database as db
from states import RegStates
from keyboards import (
    role_choice_kb,
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
            "Imtihon buyurtma qilish uchun tugmani bosing:",
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
                "yangi imtihon buyurtmalari haqida ham shu yerda xabar beriladi.",
                reply_markup=examiner_menu_kb(),
            )


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user = await db.get_user(message.from_user.id)
    if user:
        await send_menu_for_user(message, user)
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
    await db.create_user(telegram_id, role, full_name, branch, status, username)
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


@router.message(Command("admin_group"))
async def set_admin_group(message: Message):
    if message.chat.type not in ("group", "supergroup"):
        await message.answer("Bu komanda faqat guruhda ishlaydi.")
        return
    await db.set_setting("admin_group_id", str(message.chat.id))
    await message.answer(f"✅ Bu guruh admin guruh sifatida belgilandi.\nChat ID: {message.chat.id}")


@router.message(Command("whoami"))
async def whoami(message: Message):
    user = await db.get_user(message.from_user.id)
    if not user:
        await message.answer("Siz hali ro'yxatdan o'tmagansiz. /start bosing.")
        return
    await message.answer(
        f"Ism: {user['full_name']}\nRol: {user['role']}\n"
        f"Filial: {user['branch']}\nHolat: {user['status']}"
    )
