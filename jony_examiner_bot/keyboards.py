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
