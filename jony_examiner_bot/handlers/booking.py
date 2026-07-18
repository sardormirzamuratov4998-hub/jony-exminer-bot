from datetime import datetime

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State
from aiogram.filters import StateFilter

import database as db
from states import BookingStates, PostponeStates
from keyboards import (
    test_type_booking_kb,
    booking_confirm_kb,
    accept_booking_kb,
    reschedule_confirm_kb,
    cancel_kb,
    build_main_menu_kb,
    booking_branch_kb,
    repeat_fields_kb,
    repeat_group_match_kb,
    reschedule_pick_kb,
    REPEAT_FIELD_ORDER,
    postpone_pick_kb,
    postpone_confirm_kb,
)

router = Router()


async def _is_teacher(telegram_id: int):
    user = await db.get_user(telegram_id)
    return user if user and user["role"] == "TEACHER" and user["status"] != "removed" else None


async def _is_examiner(telegram_id: int):
    user = await db.get_user(telegram_id)
    return user if user and user["role"] == "EXAMINER" and user["status"] in ("active", "approved") else None


# Foydalanuvchi erkin matn kiritadigan (va shu sabab cancel_kb() ko'rsatiladigan)
# barcha bosqichlar. Bu handler shu bosqichlardagi maxsus (format tekshiruvchi)
# handlerlardan OLDIN turishi shart — shuning uchun fayl boshida joylashtirilgan.
_FREE_TEXT_BOOKING_STATES = [
    BookingStates.exam_date,
    BookingStates.exam_time,
    BookingStates.students_count,
    BookingStates.custom_field_input,
    BookingStates.repeat_group_name,
    BookingStates.repeat_exam_date,
    BookingStates.repeat_exam_time,
    BookingStates.repeat_students_count,
    PostponeStates.reason,
    PostponeStates.new_date,
    PostponeStates.new_time,
]


@router.message(StateFilter(*_FREE_TEXT_BOOKING_STATES), F.text == "❌ Bekor qilish")
async def cancel_booking_free_text(message: Message, state: FSMContext):
    await state.clear()
    is_adm = await db.is_admin(message.from_user.id)
    user = await db.get_user(message.from_user.id)
    role = user["role"] if user else None
    await message.answer("Bekor qilindi.", reply_markup=build_main_menu_kb(role, is_adm))


def _custom_fields_block(data) -> str:
    labels = data.get("custom_field_labels") or {}
    answers = data.get("custom_field_answers") or {}
    if not answers:
        return ""
    lines = [f"{labels.get(key, key)}: {value}" for key, value in answers.items()]
    return "\n" + "\n".join(lines)


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
        f"O'quvchilar soni: {data['students_count']}"
        + _custom_fields_block(data)
        + "\n\nYuborishni tasdiqlaysizmi?"
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


# =========================================================
# BUYURTMA VAQTINI KO'CHIRISH
# =========================================================

@router.message(F.text == "🕒 Vaqtni ko'chirish")
async def start_reschedule(message: Message, state: FSMContext):
    user = await _is_teacher(message.from_user.id)
    if not user:
        return

    bookings = await db.get_teacher_bookings(message.from_user.id, limit=50)
    active = [b for b in bookings if b["status"] in ("pending", "accepted")]
    if not active:
        await message.answer("Sizda hozircha vaqtini ko'chirish mumkin bo'lgan faol buyurtmalar yo'q.")
        return

    await state.set_state(BookingStates.reschedule_pick)
    await message.answer(
        "Qaysi buyurtmaning sana/vaqtini ko'chirmoqchisiz?",
        reply_markup=reschedule_pick_kb(active),
    )


@router.callback_query(BookingStates.reschedule_pick, F.data == "reschedule_cancel")
async def reschedule_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    is_adm = await db.is_admin(callback.from_user.id)
    await callback.message.edit_text("Bekor qilindi.")
    await callback.message.answer("Bosh menyu:", reply_markup=build_main_menu_kb("TEACHER", is_adm))
    await callback.answer()


@router.callback_query(BookingStates.reschedule_pick, F.data.startswith("reschedule_pick:"))
async def reschedule_pick(callback: CallbackQuery, state: FSMContext):
    booking_id = int(callback.data.split(":", 1)[1])
    booking = await db.get_booking(booking_id)
    if not booking or booking["teacher_telegram_id"] != callback.from_user.id:
        await callback.answer("Buyurtma topilmadi.", show_alert=True)
        return
    if booking["status"] not in ("pending", "accepted"):
        await callback.answer("Bu buyurtma endi faol emas.", show_alert=True)
        return

    await state.update_data(reschedule_booking_id=booking_id)
    await state.set_state(BookingStates.reschedule_date)
    await callback.message.edit_text(
        f"Tanlandi: {booking['exam_date']} {booking['exam_time']} — {booking['group_name']}\n\n"
        "Yangi sanani kiriting (masalan: 27.06.2026):"
    )
    await callback.answer()


@router.message(BookingStates.reschedule_date)
async def reschedule_get_date(message: Message, state: FSMContext):
    try:
        datetime.strptime(message.text.strip(), "%d.%m.%Y")
    except ValueError:
        await message.answer("Noto'g'ri format. Masalan: 27.06.2026 shaklida kiriting:")
        return
    await state.update_data(new_exam_date=message.text.strip())
    await state.set_state(BookingStates.reschedule_time)
    await message.answer("Yangi vaqtni kiriting (masalan: 08:00):")


@router.message(BookingStates.reschedule_time)
async def reschedule_get_time(message: Message, state: FSMContext):
    try:
        datetime.strptime(message.text.strip(), "%H:%M")
    except ValueError:
        await message.answer("Noto'g'ri format. Masalan: 08:00 shaklida kiriting:")
        return
    new_time = message.text.strip()

    data = await state.get_data()
    booking_id = data.get("reschedule_booking_id")
    new_date = data.get("new_exam_date")

    booking = await db.get_booking(booking_id)
    if not booking or booking["status"] not in ("pending", "accepted"):
        await state.clear()
        await message.answer("Bu buyurtma endi mavjud emas yoki faol emas.")
        return

    old_date, old_time = booking["exam_date"], booking["exam_time"]
    examiner_id = booking.get("examiner_telegram_id") if booking["status"] == "accepted" else None
    same_datetime = (new_date == old_date and new_time == old_time)

    # Tezkor (do'stona) tekshiruv — aniq javob esa pastdagi bo'linmas UPDATE'dan keladi.
    if examiner_id and not same_datetime:
        conflict = await db.examiner_has_conflict(examiner_id, new_date, new_time)
        if conflict:
            await message.answer(
                "Kechirasiz, biriktirilgan examinerda shu yangi sana va vaqtga "
                "allaqachon boshqa imtihon bor. Boshqa sana/vaqt kiriting, "
                "yoki /change_role yozib bekor qiling."
            )
            return

    result = await db.reschedule_booking(booking_id, new_date, new_time, examiner_id)
    if result == "conflict":
        await message.answer(
            "Kechirasiz, biriktirilgan examinerda shu yangi sana va vaqtga "
            "allaqachon boshqa imtihon bor. Boshqa sana/vaqt kiriting, "
            "yoki /change_role yozib bekor qiling."
        )
        return
    if result != "ok":
        await state.clear()
        await message.answer("Bu buyurtma endi mavjud emas yoki faol emas.")
        return

    await state.clear()

    is_adm = await db.is_admin(message.from_user.id)
    await message.answer(
        f"✅ Buyurtma vaqti ko'chirildi!\n\n"
        f"Guruh: {booking['group_name']}\n"
        f"Eski: {old_date} {old_time}\nYangi: {new_date} {new_time}",
        reply_markup=build_main_menu_kb("TEACHER", is_adm),
    )

    change_text = (
        f"🕒 <b>Buyurtma vaqti o'zgartirildi</b>\n\n"
        f"Ustoz: {booking['teacher_name']}\nFilial: {booking['branch']}\n"
        f"Guruh: {booking['group_name']}\n"
        f"Eski sana/vaqt: {old_date} {old_time}\n"
        f"Yangi sana/vaqt: {new_date} {new_time}"
    )

    # Buyurtma haqida avval xabar olgan barcha tomonlarga (filial examinerlari,
    # admin guruh, va END OF COURSE/MIDTERM bo'lsa — o'quv bo'lim rahbarlari ham) yuboriladi
    notifications = await db.get_notifications(booking_id)
    for note in notifications:
        try:
            await message.bot.send_message(note["chat_id"], change_text)
        except Exception:
            pass

    if booking["status"] == "pending":
        await message.answer(
            "Eslatma: buyurtma hali hech kim tomonidan qabul qilinmagan, "
            "yangi vaqt bilan qabul qilinishini kuting."
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
    test_types = await db.get_test_types()
    await message.answer("Test turini tanlang:", reply_markup=test_type_booking_kb(test_types))


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
        await callback.message.edit_text(f"Test turi: {test_type} ✅")
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


async def _go_to_confirm(answer_func, telegram_id: int, state: FSMContext):
    data = await state.get_data()
    user = await db.get_user(telegram_id)
    await state.set_state(BookingStates.confirm)
    await answer_func(_booking_summary(user, data), reply_markup=booking_confirm_kb())


async def _ask_next_custom_field(answer_func, telegram_id: int, state: FSMContext):
    data = await state.get_data()
    queue = data.get("custom_field_queue") or []
    if not queue:
        await _go_to_confirm(answer_func, telegram_id, state)
        return
    label = data["custom_field_labels"][queue[0]]
    await answer_func(f"{label}:")


@router.message(BookingStates.students_count)
async def get_students_count(message: Message, state: FSMContext):
    if not message.text.strip().isdigit():
        await message.answer("Faqat son kiriting:")
        return
    await state.update_data(students_count=int(message.text.strip()))

    fields = await db.get_booking_fields()
    if fields:
        await state.update_data(
            custom_field_queue=[f["field_key"] for f in fields],
            custom_field_labels={f["field_key"]: f["label"] for f in fields},
            custom_field_answers={},
        )
        await state.set_state(BookingStates.custom_field_input)
        await _ask_next_custom_field(message.answer, message.from_user.id, state)
    else:
        await state.update_data(custom_field_answers={}, custom_field_labels={})
        await _go_to_confirm(message.answer, message.from_user.id, state)


@router.message(BookingStates.custom_field_input)
async def get_custom_field_answer(message: Message, state: FSMContext):
    data = await state.get_data()
    queue = list(data.get("custom_field_queue") or [])
    if not queue:
        await _go_to_confirm(message.answer, message.from_user.id, state)
        return
    key = queue.pop(0)
    answers = dict(data.get("custom_field_answers") or {})
    answers[key] = message.text.strip()
    await state.update_data(custom_field_queue=queue, custom_field_answers=answers)
    await _ask_next_custom_field(message.answer, message.from_user.id, state)


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
    for key, value in (data.get("custom_field_answers") or {}).items():
        await db.set_booking_field_value(booking_id, key, value)
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
        + _custom_fields_block(data)
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

    # END OF COURSE / MIDTERM buyurtmalari filialdan qat'iy nazar
    # o'quv bo'lim rahbariga ham yetkaziladi
    if data["test_type"].strip().upper() in ("END OF COURSE", "MIDTERM"):
        study_heads = await db.get_active_study_heads()
        for sh in study_heads:
            try:
                sent = await callback.bot.send_message(sh["telegram_id"], text)
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

    if booking["status"] == "expired":
        await callback.answer(
            "Kechirasiz, bu imtihonning vaqti allaqachon o'tib ketgan. Uni endi qabul qilib bo'lmaydi.",
            show_alert=True,
        )
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        return

    if booking["status"] != "pending":
        msg = "Kechirasiz, bu buyurtma allaqachon band qilingan."
        if booking["examiner_name"]:
            msg = f"Kechirasiz, bu buyurtmani allaqachon {booking['examiner_name']} qabul qilgan."
        await callback.answer(msg, show_alert=True)
        return

    # Tezkor (do'stona) tekshiruv — aniq javob esa pastdagi bo'linmas UPDATE'dan keladi.
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

    # END OF COURSE / MIDTERM: examinerda shu kuni shunday imtihon bo'lsa,
    # u 2 soat davom etadi deb hisoblanadi (filialdan qat'iy nazar).
    eoc_booking, eoc_remaining = await db.examiner_eoc_conflict(
        callback.from_user.id, booking["exam_date"], booking["exam_time"]
    )
    if eoc_booking:
        eoc_finish_time = db.add_minutes_to_time(eoc_booking["exam_time"], db.EOC_DURATION_MINUTES)
        if eoc_remaining > db.EOC_NEGOTIATION_WINDOW_MINUTES:
            await callback.answer(
                f"Siz hozir {eoc_booking['test_type']} imtihonini o'tkazayapsiz, "
                f"u soat {eoc_finish_time} da tugaydi. Bu buyurtmani hozircha "
                f"qabul qila olmaysiz.",
                show_alert=True,
            )
            return

        saved = await db.propose_reschedule(
            booking_id, callback.from_user.id, examiner["full_name"], eoc_finish_time
        )
        if not saved:
            await callback.answer("Kechirasiz, bu buyurtma allaqachon band qilingan.", show_alert=True)
            return

        await callback.answer(
            "So'rov yuborildi. Ustoz tasdiqlasa, sizga biriktiriladi.", show_alert=True
        )

        try:
            await callback.bot.send_message(
                booking["teacher_telegram_id"],
                f"👋 <b>{examiner['full_name']}</b> imtihoningizni olmoqchi, lekin hozir "
                f"{eoc_booking['test_type']} imtihonini o'tkazayapti va soat "
                f"<b>{eoc_finish_time}</b> da bo'shaydi.\n\n"
                f"Imtihonni shu vaqtga ko'chirishga rozimisiz?",
                reply_markup=reschedule_confirm_kb(booking_id),
            )
        except Exception:
            pass
        return

    # YUMSHOQ KONFLIKT: examinerda shu kuni, BOSHQA filialda, 1soat 20daqiqadan
    # kam farq bilan imtihon bor — to'g'ridan-to'g'ri biriktirmasdan, avval
    # ustozdan vaqtni kechiktirishga rozimisiz deb so'raymiz.
    soft = await db.examiner_soft_conflict(
        callback.from_user.id, booking["exam_date"], booking["exam_time"], booking["branch"]
    )
    if soft:
        proposed_time = db.add_minutes_to_time(soft["exam_time"], db.SOFT_CONFLICT_BUFFER_MINUTES)
        saved = await db.propose_reschedule(
            booking_id, callback.from_user.id, examiner["full_name"], proposed_time
        )
        if not saved:
            await callback.answer("Kechirasiz, bu buyurtma allaqachon band qilingan.", show_alert=True)
            return

        await callback.answer(
            "So'rov yuborildi. Ustoz tasdiqlasa, sizga biriktiriladi.", show_alert=True
        )

        try:
            await callback.bot.send_message(
                booking["teacher_telegram_id"],
                f"👋 <b>{examiner['full_name']}</b> imtihoningizni olmoqchi, faqat "
                f"boshqa filialdan kelishga vaqt kerak.\n\n"
                f"Imtihonni soat <b>{proposed_time}</b> ga kechiktira olasizmi?",
                reply_markup=reschedule_confirm_kb(booking_id),
            )
        except Exception:
            pass
        return

    result = await db.accept_booking(
        booking_id, callback.from_user.id, examiner["full_name"],
        booking["exam_date"], booking["exam_time"],
    )
    if result == "conflict":
        await callback.answer(
            "Sizda shu sana va vaqtga allaqachon qabul qilingan boshqa imtihon bor. "
            "Bu buyurtmani qabul qila olmaysiz.",
            show_alert=True,
        )
        return
    if result != "ok":
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


@router.callback_query(F.data.startswith("resched_yes:"))
async def reschedule_confirm_yes(callback: CallbackQuery):
    booking_id = int(callback.data.split(":")[1])
    booking = await db.get_booking(booking_id)
    if not booking or booking["teacher_telegram_id"] != callback.from_user.id:
        await callback.answer("Bu so'rov sizga tegishli emas.", show_alert=True)
        return
    if not booking["pending_examiner_telegram_id"]:
        await callback.answer("Bu so'rov muddati o'tgan yoki allaqachon hal qilingan.", show_alert=True)
        return

    examiner_id = booking["pending_examiner_telegram_id"]
    examiner_name = booking["pending_examiner_name"]
    new_time = booking["pending_new_time"]

    result = await db.confirm_reschedule(booking_id)
    if result != "ok":
        await callback.answer(
            "Kechirasiz, bu buyurtma yoki examinerning vaqti allaqachon o'zgargan. "
            "So'rov endi amal qilmaydi.",
            show_alert=True,
        )
        await db.decline_reschedule(booking_id)
        return

    await callback.message.edit_text(
        (callback.message.text or "") + f"\n\n✅ Roziligingiz yuborildi. Yangi vaqt: {new_time}"
    )
    await callback.answer("Tasdiqlandi ✅")

    try:
        await callback.bot.send_message(
            examiner_id,
            f"✅ Ustoz roziligini berdi! Imtihon vaqti <b>{new_time}</b> ga ko'chirildi "
            f"va sizga biriktirildi.\n\nGuruh: {booking['group_name']}\nFilial: {booking['branch']}",
        )
    except Exception:
        pass

    notifications = await db.get_notifications(booking_id)
    for note in notifications:
        try:
            await callback.bot.edit_message_text(
                chat_id=note["chat_id"],
                message_id=note["message_id"],
                text=f"✅ Qabul qilindi: {examiner_name} (vaqt {new_time} ga ko'chirildi)",
            )
        except Exception:
            pass


@router.callback_query(F.data.startswith("resched_no:"))
async def reschedule_confirm_no(callback: CallbackQuery):
    booking_id = int(callback.data.split(":")[1])
    booking = await db.get_booking(booking_id)
    if not booking or booking["teacher_telegram_id"] != callback.from_user.id:
        await callback.answer("Bu so'rov sizga tegishli emas.", show_alert=True)
        return

    examiner_id = booking["pending_examiner_telegram_id"]
    await db.decline_reschedule(booking_id)

    await callback.message.edit_text(
        (callback.message.text or "") + "\n\n❌ Rad etdingiz. Boshqa examiner kutilmoqda."
    )
    await callback.answer("Rad etildi")

    if examiner_id:
        try:
            await callback.bot.send_message(
                examiner_id,
                "❌ Ustoz vaqtni kechiktira olmadi. So'rovingiz bekor qilindi, "
                "buyurtma boshqa examiner uchun ochiq qoldi.",
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
        test_types = await db.get_test_types()
        await answer_func("Test turini tanlang:", reply_markup=test_type_booking_kb(test_types))
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

    # 1) Avval to'liq mos kelishini tekshiramiz (masalan "Step 3 (Vikings)")
    last = await db.get_last_booking_by_group(message.from_user.id, group_name)
    if last:
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
        return

    # 2) To'liq mos kelmasa — qisman nom bo'yicha qidiramiz (masalan shunchaki "Step 3")
    matches = await db.find_teacher_group_names(message.from_user.id, group_name)
    if not matches:
        await message.answer(
            f"\"{group_name}\" nomli guruh uchun avvalgi buyurtma topilmadi. "
            "Boshqa nom kiriting yoki bekor qiling:"
        )
        return

    if len(matches) == 1:
        last = await db.get_last_booking_by_group(message.from_user.id, matches[0])
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
        return

    # 3) Bir nechta mos guruh topilsa — tanlash uchun tugmalar chiqaramiz
    await state.update_data(repeat_group_matches=matches)
    await message.answer(
        "Bir nechta mos guruh topildi, kerakligini tanlang:",
        reply_markup=repeat_group_match_kb(matches),
    )


@router.callback_query(BookingStates.repeat_group_name, F.data.startswith("repeatgroup:"))
async def choose_repeat_group_match(callback: CallbackQuery, state: FSMContext):
    idx = int(callback.data.split(":", 1)[1])
    data = await state.get_data()
    matches = data.get("repeat_group_matches") or []
    if idx >= len(matches):
        await callback.answer("Xatolik yuz berdi, qaytadan urinib ko'ring.", show_alert=True)
        return

    last = await db.get_last_booking_by_group(callback.from_user.id, matches[idx])
    if not last:
        await callback.answer("Topilmadi.", show_alert=True)
        return

    await state.update_data(
        group_name=last["group_name"],
        repeat_source=last,
        repeat_selected=[],
    )
    await state.set_state(BookingStates.repeat_fields_select)
    await callback.message.edit_text(
        _repeat_source_summary(last)
        + "\n\nQaysi ma'lumotlarni qayta kiritmoqchisiz?\n"
        "☑️ belgilangan maydonlar so'raladi, qolganlari avvalgidek qoladi.",
        reply_markup=repeat_fields_kb(set()),
    )
    await callback.answer()


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

    fields = await db.get_booking_fields()
    source_values = await db.get_booking_field_values(source["id"])
    prefill["custom_field_answers"] = {
        f["field_key"]: source_values[f["field_key"]]
        for f in fields if f["field_key"] in source_values
    }
    prefill["custom_field_labels"] = {f["field_key"]: f["label"] for f in fields}

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
        await callback.message.edit_text(f"Test turi: {test_type} ✅")
        await callback.answer()
        await _advance_repeat_queue(callback.message.answer, callback.from_user.id, state)
        return
    await callback.answer()


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


# =========================================================
# EXAMINER: QABUL QILGAN IMTIHON VAQTINI SURISH SO'ROVI
# =========================================================
# Examiner o'zi qabul qilgan (accepted) imtihonning vaqtini surishni so'raydi:
# sabab (ustozga xabar sifatida) + surish mumkin bo'lgan yangi sana/vaqt.
# Ustozga Ha/Yo'q so'raladi:
#   Ha  -> imtihon o'sha examinerda qoladi, faqat sana/vaqt yangilanadi.
#   Yo'q -> imtihon o'sha examinerdan yechiladi va BARCHA examinerlarga
#           yana bo'sh (ochiq) buyurtma sifatida e'lon qilinadi.

@router.message(F.text == "⏳ Vaqtni surish so'rash")
async def start_postpone_request(message: Message, state: FSMContext):
    user = await _is_examiner(message.from_user.id)
    if not user:
        return

    bookings = await db.get_examiner_upcoming_bookings(message.from_user.id)
    if not bookings:
        await message.answer("Sizda hozircha vaqtini surish mumkin bo'lgan qabul qilingan imtihon yo'q.")
        return

    await state.set_state(PostponeStates.pick_booking)
    await message.answer(
        "Qaysi imtihonning vaqtini surishni so'ramoqchisiz?",
        reply_markup=postpone_pick_kb(bookings),
    )


@router.callback_query(PostponeStates.pick_booking, F.data == "postpone_cancel")
async def postpone_pick_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    is_adm = await db.is_admin(callback.from_user.id)
    await callback.message.edit_text("Bekor qilindi.")
    await callback.message.answer("Bosh menyu:", reply_markup=build_main_menu_kb("EXAMINER", is_adm))
    await callback.answer()


@router.callback_query(PostponeStates.pick_booking, F.data.startswith("postpone_pick:"))
async def postpone_pick(callback: CallbackQuery, state: FSMContext):
    booking_id = int(callback.data.split(":", 1)[1])
    booking = await db.get_booking(booking_id)
    if (
        not booking
        or booking["status"] != "accepted"
        or booking["examiner_telegram_id"] != callback.from_user.id
    ):
        await callback.answer("Bu imtihon endi mavjud emas.", show_alert=True)
        return

    await state.update_data(postpone_booking_id=booking_id)
    await state.set_state(PostponeStates.reason)
    await callback.message.edit_text(
        f"Tanlandi: {booking['exam_date']} {booking['exam_time']} — {booking['group_name']}\n\n"
        "Sababini yozing (bu xabar ustozga yuboriladi):"
    )
    await callback.message.answer("Yozing 👇", reply_markup=cancel_kb())
    await callback.answer()


@router.message(PostponeStates.reason)
async def postpone_get_reason(message: Message, state: FSMContext):
    reason = message.text.strip()
    if not reason:
        await message.answer("Iltimos, sababini yozing:")
        return
    await state.update_data(postpone_reason=reason)
    await state.set_state(PostponeStates.new_date)
    await message.answer("Surish mumkin bo'lgan sanani kiriting (masalan: 27.06.2026):")


@router.message(PostponeStates.new_date)
async def postpone_get_new_date(message: Message, state: FSMContext):
    try:
        datetime.strptime(message.text.strip(), "%d.%m.%Y")
    except ValueError:
        await message.answer("Noto'g'ri format. Masalan: 27.06.2026 shaklida kiriting:")
        return
    await state.update_data(postpone_new_date=message.text.strip())
    await state.set_state(PostponeStates.new_time)
    await message.answer("Surish mumkin bo'lgan vaqtni kiriting (masalan: 08:00):")


@router.message(PostponeStates.new_time)
async def postpone_get_new_time(message: Message, state: FSMContext):
    try:
        datetime.strptime(message.text.strip(), "%H:%M")
    except ValueError:
        await message.answer("Noto'g'ri format. Masalan: 08:00 shaklida kiriting:")
        return
    new_time = message.text.strip()

    data = await state.get_data()
    booking_id = data.get("postpone_booking_id")
    reason = data.get("postpone_reason")
    new_date = data.get("postpone_new_date")

    booking = await db.get_booking(booking_id)
    if (
        not booking
        or booking["status"] != "accepted"
        or booking["examiner_telegram_id"] != message.from_user.id
    ):
        await state.clear()
        await message.answer("Bu imtihon endi mavjud emas yoki sizga biriktirilgan emas.")
        return

    saved = await db.request_postpone(booking_id, message.from_user.id, reason, new_date, new_time)
    if not saved:
        await state.clear()
        await message.answer("Bu imtihon endi mavjud emas yoki sizga biriktirilgan emas.")
        return

    await state.clear()
    is_adm = await db.is_admin(message.from_user.id)
    await message.answer(
        "✅ So'rovingiz ustozga yuborildi. Javobini kuting.",
        reply_markup=build_main_menu_kb("EXAMINER", is_adm),
    )

    examiner = await db.get_user(message.from_user.id)
    try:
        await message.bot.send_message(
            booking["teacher_telegram_id"],
            f"⏳ <b>Imtihon vaqtini surish so'rovi</b>\n\n"
            f"Examiner: {examiner['full_name'] if examiner else booking['examiner_name']}\n"
            f"Filial: {booking['branch']}\nGuruh: {booking['group_name']}\n"
            f"Hozirgi sana/vaqt: {booking['exam_date']} {booking['exam_time']}\n\n"
            f"Sabab: {reason}\n\n"
            f"Taklif qilingan yangi sana/vaqt: <b>{new_date} {new_time}</b>\n\n"
            "Rozimisiz?",
            reply_markup=postpone_confirm_kb(booking_id),
        )
    except Exception:
        pass


@router.callback_query(F.data.startswith("postpone_yes:"))
async def postpone_confirm_yes(callback: CallbackQuery):
    booking_id = int(callback.data.split(":")[1])
    booking = await db.get_booking(booking_id)
    if not booking or booking["teacher_telegram_id"] != callback.from_user.id:
        await callback.answer("Bu so'rov sizga tegishli emas.", show_alert=True)
        return
    if not booking.get("postpone_new_date"):
        await callback.answer("Bu so'rov muddati o'tgan yoki allaqachon hal qilingan.", show_alert=True)
        return

    old_date, old_time = booking["exam_date"], booking["exam_time"]
    new_date, new_time = booking["postpone_new_date"], booking["postpone_new_time"]
    examiner_id = booking["examiner_telegram_id"]
    examiner_name = booking["examiner_name"]

    result = await db.approve_postpone(booking_id)
    if result == "conflict":
        await db.clear_postpone(booking_id)
        await callback.message.edit_text(
            (callback.message.text or "")
            + "\n\n⚠️ Kechirasiz, examinerda bu yangi vaqtga endi boshqa imtihon bor. So'rov bekor qilindi."
        )
        await callback.answer("Konflikt aniqlandi", show_alert=True)
        try:
            await callback.bot.send_message(
                examiner_id,
                "⚠️ Ustoz rozi bo'lgan edi, lekin siz bu orada shu vaqtga boshqa imtihon "
                "qabul qilib ulgurgansiz. So'rov bekor qilindi, eski vaqt kuchda qoladi.",
            )
        except Exception:
            pass
        return
    if result != "ok":
        await callback.answer("Bu so'rov endi amal qilmaydi.", show_alert=True)
        return

    await callback.message.edit_text(
        (callback.message.text or "") + f"\n\n✅ Roziligingiz yuborildi. Yangi vaqt: {new_date} {new_time}"
    )
    await callback.answer("Tasdiqlandi ✅")

    try:
        await callback.bot.send_message(
            examiner_id,
            f"✅ Ustoz roziligini berdi! Imtihon vaqti <b>{new_date} {new_time}</b> ga ko'chirildi.\n\n"
            f"Guruh: {booking['group_name']}\nFilial: {booking['branch']}",
        )
    except Exception:
        pass

    change_text = (
        f"🕒 <b>Buyurtma vaqti o'zgartirildi</b>\n\n"
        f"Ustoz: {booking['teacher_name']}\nFilial: {booking['branch']}\n"
        f"Guruh: {booking['group_name']}\nExaminer: {examiner_name}\n"
        f"Eski sana/vaqt: {old_date} {old_time}\n"
        f"Yangi sana/vaqt: {new_date} {new_time}"
    )
    notifications = await db.get_notifications(booking_id)
    for note in notifications:
        try:
            await callback.bot.send_message(note["chat_id"], change_text)
        except Exception:
            pass


@router.callback_query(F.data.startswith("postpone_no:"))
async def postpone_confirm_no(callback: CallbackQuery):
    booking_id = int(callback.data.split(":")[1])
    booking = await db.get_booking(booking_id)
    if not booking or booking["teacher_telegram_id"] != callback.from_user.id:
        await callback.answer("Bu so'rov sizga tegishli emas.", show_alert=True)
        return
    if not booking.get("postpone_new_date"):
        await callback.answer("Bu so'rov muddati o'tgan yoki allaqachon hal qilingan.", show_alert=True)
        return

    examiner_id = booking["examiner_telegram_id"]

    result = await db.decline_postpone(booking_id)
    if not result:
        await callback.answer("Bu so'rov endi amal qilmaydi.", show_alert=True)
        return

    await callback.message.edit_text(
        (callback.message.text or "")
        + "\n\n❌ Rad etdingiz. Imtihon examinerdan yechildi va boshqa examinerlarga ochiq buyurtma sifatida yuborildi."
    )
    await callback.answer("Rad etildi")

    if examiner_id:
        try:
            await callback.bot.send_message(
                examiner_id,
                "❌ Ustoz vaqtni surishga rozi bo'lmadi. Imtihon sizdan yechildi va boshqa "
                "examinerlarga ochiq buyurtma sifatida yuborildi.",
            )
        except Exception:
            pass

    text = (
        f"🔔 <b>Bo'sh imtihon buyurtmasi</b>\n\n"
        f"Ustoz: {booking['teacher_name']}\n"
        f"Filial: {booking['branch']}\n"
        f"Sana: {booking['exam_date']}\n"
        f"Vaqt: {booking['exam_time']}\n"
        f"Test turi: {booking['test_type']}"
        + (f" ({booking['test_name']})" if booking.get("test_name") else "")
        + f"\nGuruh: {booking['group_name']}\n"
        f"O'quvchilar soni: {booking['students_count']}"
    )
    examiners = await db.get_examiners_by_branch(booking["branch"])
    for ex in examiners:
        if ex["telegram_id"] == examiner_id:
            continue
        try:
            sent = await callback.bot.send_message(
                ex["telegram_id"], text, reply_markup=accept_booking_kb(booking_id)
            )
            await db.add_notification(booking_id, sent.chat.id, sent.message_id)
        except Exception:
            pass
