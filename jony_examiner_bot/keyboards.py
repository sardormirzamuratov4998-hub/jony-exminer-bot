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


def entry_mode_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="📋 Ro'yxatni bir xabarda yuborish (tezroq)", callback_data="entry_mode:bulk")
    builder.button(text="📝 Birma-bir kiritish", callback_data="entry_mode:single")
    builder.adjust(1)
    return builder.as_markup()


def retake_checkbox_kb(students, selected):
    """selected = index'ga QO'SHILMAYDIGAN (belgilangan) o'quvchilar to'plami."""
    builder = InlineKeyboardBuilder()
    for i, s in enumerate(students):
        mark = "☑️" if i in selected else "⬜️"
        builder.button(
            text=f"{mark} {s['surname']} {s['name']}", callback_data=f"idx_toggle:{i}"
        )
    builder.button(text="✏️ Ismlarni yozib chiqish", callback_data="idx_manual")
    builder.button(text="✅ Tasdiqlash va Excel yaratish", callback_data="idx_confirm")
    builder.adjust(1)
    return builder.as_markup()


def retake_kb(students, selected):
    builder = InlineKeyboardBuilder()
    for i, s in enumerate(students):
        mark = "🚫" if i in selected else "⬜️"
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
    builder.button(text="🛠 Adminman", callback_data="role:ADMIN")
    builder.adjust(1)
    return builder.as_markup()


def branch_kb(prefix="branch", exclude=None):
    exclude = exclude or []
    builder = InlineKeyboardBuilder()
    for b in BRANCHES:
        if b in exclude:
            continue
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


def midterm_type_choice_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="📕 END OF COURSE", callback_data="midterm_choice:END OF COURSE")
    builder.button(text="📗 MIDTERM", callback_data="midterm_choice:MIDTERM")
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


def build_main_menu_kb(role: str = None, is_admin: bool = False):
    """Rolga mos tugma(lar) + agar admin bo'lsa qo'shimcha Admin panel tugmasi."""
    builder = ReplyKeyboardBuilder()
    if role == "TEACHER":
        builder.button(text="📅 Imtihon buyurtma qilish")
        builder.button(text="➕ Filial qo'shish")
    elif role == "EXAMINER":
        builder.button(text="🆕 Test kiritish")
    if is_admin:
        builder.button(text="🛠 Admin panel")
    builder.adjust(1)
    return builder.as_markup(resize_keyboard=True)


def admin_only_menu_kb():
    builder = ReplyKeyboardBuilder()
    builder.button(text="🛠 Admin panel")
    builder.adjust(1)
    return builder.as_markup(resize_keyboard=True)


def booking_branch_kb(branches):
    builder = InlineKeyboardBuilder()
    for b in branches:
        builder.button(text=b, callback_data=f"bookbranch:{b}")
    builder.adjust(1)
    return builder.as_markup()


def admin_panel_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="📋 Kutilayotgan examinerlar", callback_data="admin_pending")
    builder.button(text="📅 Faol buyurtmalar", callback_data="admin_bookings")
    builder.button(text="👤 Xodimlar (o'chirish)", callback_data="admin_staff")
    builder.button(text="🛡 Adminlar ro'yxati", callback_data="admin_admins")
    builder.button(text="➕ Admin qo'shish", callback_data="admin_add")
    builder.button(text="📊 Kunlik hisobot (hozir)", callback_data="admin_daily_report")
    builder.button(text="ℹ️ Admin guruh sozlash", callback_data="admin_group_info")
    builder.adjust(1)
    return builder.as_markup()
