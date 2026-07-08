from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder


def start_kb():
    builder = ReplyKeyboardBuilder()
    builder.button(text="🆕 Test kiritish")
    builder.adjust(1)
    return builder.as_markup(resize_keyboard=True)


def test_type_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="📘 UNIT TEST", callback_data="test_type:unit")
    builder.button(text="📗 MIDTERM / O'TISH TESTI", callback_data="test_type:midterm")
    builder.adjust(1)
    return builder.as_markup()


def sections_confirm_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Standart (20/25/40/15)", callback_data="sections:default")
    builder.button(text="✏️ O'zgartirish", callback_data="sections:edit")
    builder.adjust(1)
    return builder.as_markup()


def after_student_kb():
    builder = ReplyKeyboardBuilder()
    builder.button(text="➕ O'quvchi qo'shish")
    builder.button(text="✅ Tayyor")
    builder.adjust(1)
    return builder.as_markup(resize_keyboard=True)


def retake_kb(students, selected):
    builder = InlineKeyboardBuilder()
    for i, s in enumerate(students):
        mark = "☑️" if i in selected else "⬜️"
        builder.button(
            text=f"{mark} {s['surname']} {s['name']}",
            callback_data=f"retake_toggle:{i}",
        )
    builder.button(text="✏️ Qo'lda ism-familiya yozish", callback_data="retake_manual")
    builder.button(text="✅ Tasdiqlash va Excel yaratish", callback_data="retake_confirm")
    builder.adjust(1)
    return builder.as_markup()


def cancel_kb():
    builder = ReplyKeyboardBuilder()
    builder.button(text="❌ Bekor qilish")
    builder.adjust(1)
    return builder.as_markup(resize_keyboard=True)


# ---------- ROLE / BOOKING KEYBOARDS ----------

BRANCHES = ["Zafar", "Bekobod", "Stretinka"]


def role_choice_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="👩‍🏫 Men Ustozman", callback_data="role:TEACHER")
    builder.button(text="🧑‍💼 Men Examinerman", callback_data="role:EXAMINER")
    builder.adjust(1)
    return builder.as_markup()


def branch_kb(prefix="branch"):
    builder = InlineKeyboardBuilder()
    for b in BRANCHES:
        builder.button(text=b, callback_data=f"{prefix}:{b}")
    builder.adjust(1)
    return builder.as_markup()


def teacher_menu_kb():
    builder = ReplyKeyboardBuilder()
    builder.button(text="📅 Imtihon buyurtma qilish")
    builder.adjust(1)
    return builder.as_markup(resize_keyboard=True)


def examiner_menu_kb():
    builder = ReplyKeyboardBuilder()
    builder.button(text="🆕 Test kiritish")
    builder.adjust(1)
    return builder.as_markup(resize_keyboard=True)


def test_type_booking_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="📘 UNIT TEST", callback_data="booking_type:UNIT TEST")
    builder.button(text="📗 END OF COURSE / MIDTERM", callback_data="booking_type:END OF COURSE / MIDTERM")
    builder.adjust(1)
    return builder.as_markup()


def booking_confirm_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Yuborish", callback_data="booking_confirm")
    builder.button(text="❌ Bekor qilish", callback_data="booking_cancel")
    builder.adjust(1)
    return builder.as_markup()


def accept_booking_kb(booking_id: int):
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Qabul qilish", callback_data=f"accept_booking:{booking_id}")
    builder.adjust(1)
    return builder.as_markup()


def examiner_approve_kb(telegram_id: int):
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Tasdiqlash", callback_data=f"approve_examiner:{telegram_id}")
    builder.button(text="❌ Rad etish", callback_data=f"reject_examiner:{telegram_id}")
    builder.adjust(2)
    return builder.as_markup()
