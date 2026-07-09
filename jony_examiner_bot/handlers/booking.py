from datetime import datetime

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

import database as db
from states import BookingStates
from keyboards import (
    test_type_booking_kb,
    booking_confirm_kb,
    accept_booking_kb,
    cancel_kb,
    build_main_menu_kb,
    booking_branch_kb,
)

router = Router()


async def _is_teacher(telegram_id: int):
    user = await db.get_user(telegram_id)
    return user if user and user["role"] == "TEACHER" else None


@router.message(F.text == "📅 Imtihon buyurtma qilish")
async def start_booking(message: Message, state: FSMContext):
    user = await _is_teacher(message.from_user.id)
    if not user:
        return

    branches = await db.get_teacher_branches(message.from_user.id)
    if not branches:
        branches = [user["branch"]]

    if len(branches) == 1:
        await state.update_data(branch=branches[0])
        await state.set_state(BookingStates.exam_date)
        await message.answer(
            "Imtihon sanasini kiriting (masalan: 27.06.2026):",
            reply_markup=cancel_kb(),
        )
    else:
        await state.set_state(BookingStates.choose_branch)
        await message.answer(
            "Qaysi filial uchun buyurtma qilyapsiz?",
            reply_markup=booking_branch_kb(branches),
        )


@router.callback_query(BookingStates.choose_branch, F.data.startswith("bookbranch:"))
async def choose_booking_branch(callback: CallbackQuery, state: FSMContext):
    branch = callback.data.split(":", 1)[1]
    await state.update_data(branch=branch)
    await state.set_state(BookingStates.exam_date)
    await callback.message.edit_text(f"Filial: {branch} ✅")
    await callback.message.answer("Imtihon sanasini kiriting (masalan: 27.06.2026):")
    await callback.answer()


@router.message(BookingStates.exam_date)
async def get_exam_date(message: Message, state: FSMContext):
    try:
        datetime.strptime(message.text.strip(), "%d.%m.%Y")
    except ValueError:
        await message.answer("Noto'g'ri format. Masalan: 27.06.2026 shaklida kiriting:")
        return
    await state.update_data(exam_date=message.text.strip())
    await state.set_state(BookingStates.exam_time)
    await message.answer("Imtihon vaqtini kiriting (masalan: 08:00):")


@router.message(BookingStates.exam_time)
async def get_exam_time(message: Message, state: FSMContext):
    try:
        datetime.strptime(message.text.strip(), "%H:%M")
    except ValueError:
        await message.answer("Noto'g'ri format. Masalan: 08:00 shaklida kiriting:")
        return
    await state.update_data(exam_time=message.text.strip())
    await state.set_state(BookingStates.test_type)
    await message.answer("Test turini tanlang:", reply_markup=test_type_booking_kb())


@router.callback_query(BookingStates.test_type, F.data.startswith("booking_type:"))
async def get_test_type(callback: CallbackQuery, state: FSMContext):
    test_type = callback.data.split(":", 1)[1]
    await state.update_data(test_type=test_type)
    if test_type == "UNIT TEST":
        await state.set_state(BookingStates.unit_name)
        await callback.message.edit_text("Unit raqamini kiriting (masalan: Unit 7):")
    else:
        await state.update_data(test_name=None)
        await state.set_state(BookingStates.group_name)
        await callback.message.edit_text(
            "Guruh/Daraja nomini kiriting (masalan: Step 3 (Vikings)):"
        )
    await callback.answer()


@router.message(BookingStates.unit_name)
async def get_unit_name(message: Message, state: FSMContext):
    await state.update_data(test_name=message.text.strip())
    await state.set_state(BookingStates.group_name)
    await message.answer("Guruh/Daraja nomini kiriting (masalan: Step 3 (Vikings)):")


@router.message(BookingStates.group_name)
async def get_group_name(message: Message, state: FSMContext):
    await state.update_data(group_name=message.text.strip())
    await state.set_state(BookingStates.students_count)
    await message.answer("O'quvchilar sonini kiriting:")


@router.message(BookingStates.students_count)
async def get_students_count(message: Message, state: FSMContext):
    if not message.text.strip().isdigit():
        await message.answer("Faqat son kiriting:")
        return
    await state.update_data(students_count=int(message.text.strip()))
    data = await state.get_data()
    user = await db.get_user(message.from_user.id)

    summary = (
        "📋 <b>Buyurtma ma'lumotlari:</b>\n\n"
        f"Ustoz: {user['full_name']}\n"
        f"Filial: {data['branch']}\n"
        f"Sana: {data['exam_date']}\n"
        f"Vaqt: {data['exam_time']}\n"
        f"Test turi: {data['test_type']}"
        + (f" ({data['test_name']})" if data.get("test_name") else "")
        + f"\nGuruh: {data['group_name']}\n"
        f"O'quvchilar soni: {data['students_count']}\n\n"
        "Yuborishni tasdiqlaysizmi?"
    )
    await state.set_state(BookingStates.confirm)
    await message.answer(summary, reply_markup=booking_confirm_kb())


@router.callback_query(BookingStates.confirm, F.data == "booking_cancel")
async def booking_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    is_adm = await db.is_admin(callback.from_user.id)
    await callback.message.edit_text("Bekor qilindi.")
    await callback.message.answer("Bosh menyu:", reply_markup=build_main_menu_kb("TEACHER", is_adm))
    await callback.answer()


@router.callback_query(BookingStates.confirm, F.data == "booking_confirm")
async def booking_confirm(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    user = await db.get_user(callback.from_user.id)

    booking_id = await db.create_booking({
        "teacher_telegram_id": callback.from_user.id,
        "teacher_name": user["full_name"],
        "branch": data["branch"],
        "exam_date": data["exam_date"],
        "exam_time": data["exam_time"],
        "test_type": data["test_type"],
        "test_name": data.get("test_name"),
        "group_name": data["group_name"],
        "students_count": data["students_count"],
    })
    await state.clear()

    is_adm = await db.is_admin(callback.from_user.id)
    await callback.message.edit_text("✅ Buyurtmangiz yuborildi! Examiner qabul qilishini kuting.")
    await callback.message.answer("Bosh menyu:", reply_markup=build_main_menu_kb("TEACHER", is_adm))

    text = (
        f"🔔 <b>Yangi imtihon buyurtmasi</b>\n\n"
        f"Ustoz: {user['full_name']}\n"
        f"Filial: {data['branch']}\n"
        f"Sana: {data['exam_date']}\n"
        f"Vaqt: {data['exam_time']}\n"
        f"Test turi: {data['test_type']}"
        + (f" ({data['test_name']})" if data.get("test_name") else "")
        + f"\nGuruh: {data['group_name']}\n"
        f"O'quvchilar soni: {data['students_count']}"
    )

    examiners = await db.get_examiners_by_branch(data["branch"])
    for ex in examiners:
        try:
            sent = await callback.bot.send_message(
                ex["telegram_id"], text, reply_markup=accept_booking_kb(booking_id)
            )
            await db.add_notification(booking_id, sent.chat.id, sent.message_id)
        except Exception:
            pass

    admin_group_id = await db.get_setting("admin_group_id")
    if admin_group_id:
        try:
            sent = await callback.bot.send_message(int(admin_group_id), text)
            await db.add_notification(booking_id, sent.chat.id, sent.message_id)
        except Exception:
            pass

    await callback.answer()


@router.callback_query(F.data.startswith("accept_booking:"))
async def accept_booking_handler(callback: CallbackQuery):
    booking_id = int(callback.data.split(":")[1])
    booking = await db.get_booking(booking_id)
    if not booking:
        await callback.answer("Buyurtma topilmadi.", show_alert=True)
        return

    if booking["status"] != "pending":
        msg = "Kechirasiz, bu buyurtma allaqachon band qilingan."
        if booking["examiner_name"]:
            msg = f"Kechirasiz, bu buyurtmani allaqachon {booking['examiner_name']} qabul qilgan."
        await callback.answer(msg, show_alert=True)
        return

    conflict = await db.examiner_has_conflict(
        callback.from_user.id, booking["exam_date"], booking["exam_time"]
    )
    if conflict:
        await callback.answer(
            "Sizda shu sana va vaqtga allaqachon qabul qilingan imtihon bor. "
            "Bu buyurtmani qabul qila olmaysiz.",
            show_alert=True,
        )
        return

    examiner = await db.get_user(callback.from_user.id)
    success = await db.accept_booking(booking_id, callback.from_user.id, examiner["full_name"])
    if not success:
        await callback.answer("Kechirasiz, bu buyurtma allaqachon band qilingan.", show_alert=True)
        return

    await callback.answer("Qabul qilindi ✅")

    notifications = await db.get_notifications(booking_id)
    for note in notifications:
        try:
            await callback.bot.edit_message_text(
                chat_id=note["chat_id"],
                message_id=note["message_id"],
                text=(callback.message.text or "") + f"\n\n✅ Qabul qilindi: {examiner['full_name']}",
            )
        except Exception:
            pass

    try:
        await callback.bot.send_message(
            booking["teacher_telegram_id"],
            f"✅ Imtihoningizni <b>{examiner['full_name']}</b> qabul qildi!\n\n"
            f"Sana: {booking['exam_date']}\nVaqt: {booking['exam_time']}",
        )
    except Exception:
        pass
