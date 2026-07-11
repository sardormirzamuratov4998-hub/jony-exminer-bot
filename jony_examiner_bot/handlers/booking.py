from datetime import datetime

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

import database as db
from states import BookingStates
from keyboards import (
    test_type_booking_kb,
    midterm_type_choice_kb,
    booking_confirm_kb,
    accept_booking_kb,
    cancel_kb,
    build_main_menu_kb,
    booking_branch_kb,
    repeat_fields_kb,
    REPEAT_FIELD_ORDER,
)

router = Router()


async def _is_teacher(telegram_id: int):
    user = await db.get_user(telegram_id)
    return user if user and user["role"] == "TEACHER" else None


def _booking_summary(user, data) -> str:
    return (
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


_STATUS_LABELS = {
    "pending": ("🟡", "Kutilmoqda"),
    "accepted": ("🟢", "Qabul qilingan"),
    "cancelled": ("🔴", "Bekor qilingan"),
    "expired": ("⚪️", "Muddati o'tgan"),
}


@router.message(F.text == "📋 Mening buyurtmalarim")
async def my_bookings(message: Message):
    user = await _is_teacher(message.from_user.id)
    if not user:
        return

    bookings = await db.get_teacher_bookings(message.from_user.id)
    if not bookings:
        await message.answer("Sizda hozircha buyurtmalar yo'q.")
        return

    lines = ["📋 <b>Mening buyurtmalarim:</b>"]
    for b in bookings:
        emoji, label = _STATUS_LABELS.get(b["status"], ("⚪️", b["status"]))
        test_info = b["test_type"]
        if b.get("test_name"):
            test_info += f" ({b['test_name']})"
        examiner_line = f"\nExaminer: {b['examiner_name']}" if b.get("examiner_name") else ""
        lines.append(
            f"\n{emoji} <b>{b['exam_date']} {b['exam_time']}</b> — {label}\n"
            f"Filial: {b['branch']}\nGuruh: {b['group_name']}\n"
            f"Turi: {test_info}\nO'quvchilar soni: {b['students_count']}"
            f"{examiner_line}"
        )
    await message.answer("\n".join(lines))


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
        await state.set_state(BookingStates.midterm_choice)
        await callback.message.edit_text(
            "Aynan qaysi turi?", reply_markup=midterm_type_choice_kb()
        )
    await callback.answer()


@router.callback_query(BookingStates.midterm_choice, F.data.startswith("midterm_choice:"))
async def choose_midterm_type(callback: CallbackQuery, state: FSMContext):
    choice = callback.data.split(":", 1)[1]
    await state.update_data(test_type=choice)
    await state.set_state(BookingStates.group_name)
    await callback.message.edit_text(f"Test turi: {choice} ✅")
    await callback.message.answer("Guruh/Daraja nomini kiriting (masalan: Step 3 (Vikings)):")
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

    await state.set_state(BookingStates.confirm)
    await message.answer(_booking_summary(user, data), reply_markup=booking_confirm_kb())


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


# =========================================================
# OXIRGI BUYURTMANI TAKRORLASH (avval imtihon topshirgan guruh)
# =========================================================

def _repeat_source_summary(b: dict) -> str:
    test_info = b["test_type"]
    if b.get("test_name"):
        test_info += f" ({b['test_name']})"
    return (
        f"🔁 Topilgan oxirgi buyurtma — <b>{b['group_name']}</b>:\n"
        f"Filial: {b['branch']}\nSana: {b['exam_date']}\nVaqt: {b['exam_time']}\n"
        f"Test turi: {test_info}\nO'quvchilar soni: {b['students_count']}"
    )


async def _advance_repeat_queue(answer_func, telegram_id: int, state: FSMContext):
    """Navbatdagi belgilangan maydonni so'raydi; navbat tugasa — yakuniy tasdiqlashni ko'rsatadi."""
    data = await state.get_data()
    queue = list(data.get("repeat_queue", []))

    if not queue:
        user = await db.get_user(telegram_id)
        await state.set_state(BookingStates.confirm)
        await answer_func(_booking_summary(user, data), reply_markup=booking_confirm_kb())
        return

    field = queue[0]
    await state.update_data(repeat_queue=queue[1:])

    if field == "branch":
        user = await db.get_user(telegram_id)
        branches = await db.get_teacher_branches(telegram_id)
        if not branches:
            branches = [user["branch"]]
        await state.set_state(BookingStates.repeat_branch)
        await answer_func("Qaysi filial uchun buyurtma qilyapsiz?", reply_markup=booking_branch_kb(branches))
    elif field == "exam_date":
        await state.set_state(BookingStates.repeat_exam_date)
        await answer_func("Imtihon sanasini kiriting (masalan: 27.06.2026):")
    elif field == "exam_time":
        await state.set_state(BookingStates.repeat_exam_time)
        await answer_func("Imtihon vaqtini kiriting (masalan: 08:00):")
    elif field == "test_type":
        await state.set_state(BookingStates.repeat_test_type)
        await answer_func("Test turini tanlang:", reply_markup=test_type_booking_kb())
    elif field == "students_count":
        await state.set_state(BookingStates.repeat_students_count)
        await answer_func("O'quvchilar sonini kiriting:")


@router.message(F.text == "🔁 avval imtihon topshirgan guruh")
async def start_repeat_booking(message: Message, state: FSMContext):
    user = await _is_teacher(message.from_user.id)
    if not user:
        return

    await state.set_state(BookingStates.repeat_group_name)
    await message.answer(
        "Avval imtihon topshirgan guruh nomini kiriting (masalan: Step 3 (Vikings)):",
        reply_markup=cancel_kb(),
    )


@router.message(BookingStates.repeat_group_name)
async def get_repeat_group_name(message: Message, state: FSMContext):
    group_name = message.text.strip()
    last = await db.get_last_booking_by_group(message.from_user.id, group_name)
    if not last:
        await message.answer(
            f"\"{group_name}\" nomli guruh uchun avvalgi buyurtma topilmadi. "
            "Boshqa nom kiriting yoki bekor qiling:"
        )
        return

    await state.update_data(
        group_name=last["group_name"],
        repeat_source=last,
        repeat_selected=[],
    )
    await state.set_state(BookingStates.repeat_fields_select)
    await message.answer(
        _repeat_source_summary(last)
        + "\n\nQaysi ma'lumotlarni qayta kiritmoqchisiz?\n"
        "☑️ belgilangan maydonlar so'raladi, qolganlari avvalgidek qoladi.",
        reply_markup=repeat_fields_kb(set()),
    )


@router.callback_query(BookingStates.repeat_fields_select, F.data.startswith("repeat_toggle:"))
async def toggle_repeat_field(callback: CallbackQuery, state: FSMContext):
    key = callback.data.split(":", 1)[1]
    data = await state.get_data()
    selected = set(data.get("repeat_selected", []))
    if key in selected:
        selected.discard(key)
    else:
        selected.add(key)
    await state.update_data(repeat_selected=list(selected))
    await callback.message.edit_reply_markup(reply_markup=repeat_fields_kb(selected))
    await callback.answer()


@router.callback_query(BookingStates.repeat_fields_select, F.data == "repeat_cancel")
async def cancel_repeat_booking(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    is_adm = await db.is_admin(callback.from_user.id)
    await callback.message.edit_text("Bekor qilindi.")
    await callback.message.answer("Bosh menyu:", reply_markup=build_main_menu_kb("TEACHER", is_adm))
    await callback.answer()


@router.callback_query(BookingStates.repeat_fields_select, F.data == "repeat_start")
async def repeat_start(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected = set(data.get("repeat_selected", []))
    source = data["repeat_source"]

    prefill = {}
    if "branch" not in selected:
        prefill["branch"] = source["branch"]
    if "exam_date" not in selected:
        prefill["exam_date"] = source["exam_date"]
    if "exam_time" not in selected:
        prefill["exam_time"] = source["exam_time"]
    if "test_type" not in selected:
        prefill["test_type"] = source["test_type"]
        prefill["test_name"] = source.get("test_name")
    if "students_count" not in selected:
        prefill["students_count"] = source["students_count"]

    queue = [f for f in REPEAT_FIELD_ORDER if f in selected]
    await state.update_data(**prefill, repeat_queue=queue)

    await callback.message.edit_text("Davom etilmoqda... ⏳")
    await callback.answer()
    await _advance_repeat_queue(callback.message.answer, callback.from_user.id, state)


@router.callback_query(BookingStates.repeat_branch, F.data.startswith("bookbranch:"))
async def choose_repeat_branch(callback: CallbackQuery, state: FSMContext):
    branch = callback.data.split(":", 1)[1]
    await state.update_data(branch=branch)
    await callback.message.edit_text(f"Filial: {branch} ✅")
    await callback.answer()
    await _advance_repeat_queue(callback.message.answer, callback.from_user.id, state)


@router.message(BookingStates.repeat_exam_date)
async def get_repeat_exam_date(message: Message, state: FSMContext):
    try:
        datetime.strptime(message.text.strip(), "%d.%m.%Y")
    except ValueError:
        await message.answer("Noto'g'ri format. Masalan: 27.06.2026 shaklida kiriting:")
        return
    await state.update_data(exam_date=message.text.strip())
    await _advance_repeat_queue(message.answer, message.from_user.id, state)


@router.message(BookingStates.repeat_exam_time)
async def get_repeat_exam_time(message: Message, state: FSMContext):
    try:
        datetime.strptime(message.text.strip(), "%H:%M")
    except ValueError:
        await message.answer("Noto'g'ri format. Masalan: 08:00 shaklida kiriting:")
        return
    await state.update_data(exam_time=message.text.strip())
    await _advance_repeat_queue(message.answer, message.from_user.id, state)


@router.callback_query(BookingStates.repeat_test_type, F.data.startswith("booking_type:"))
async def get_repeat_test_type(callback: CallbackQuery, state: FSMContext):
    test_type = callback.data.split(":", 1)[1]
    await state.update_data(test_type=test_type)
    if test_type == "UNIT TEST":
        await state.set_state(BookingStates.repeat_unit_name)
        await callback.message.edit_text("Unit raqamini kiriting (masalan: Unit 7):")
    else:
        await state.update_data(test_name=None)
        await state.set_state(BookingStates.repeat_midterm_choice)
        await callback.message.edit_text("Aynan qaysi turi?", reply_markup=midterm_type_choice_kb())
    await callback.answer()


@router.callback_query(BookingStates.repeat_midterm_choice, F.data.startswith("midterm_choice:"))
async def choose_repeat_midterm_type(callback: CallbackQuery, state: FSMContext):
    choice = callback.data.split(":", 1)[1]
    await state.update_data(test_type=choice)
    await callback.message.edit_text(f"Test turi: {choice} ✅")
    await callback.answer()
    await _advance_repeat_queue(callback.message.answer, callback.from_user.id, state)


@router.message(BookingStates.repeat_unit_name)
async def get_repeat_unit_name(message: Message, state: FSMContext):
    await state.update_data(test_name=message.text.strip())
    await _advance_repeat_queue(message.answer, message.from_user.id, state)


@router.message(BookingStates.repeat_students_count)
async def get_repeat_students_count(message: Message, state: FSMContext):
    if not message.text.strip().isdigit():
        await message.answer("Faqat son kiriting:")
        return
    await state.update_data(students_count=int(message.text.strip()))
    await _advance_repeat_queue(message.answer, message.from_user.id, state)
