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
    builder.button(text="✏️ Tuzatish / O'chirish")
    builder.button(text="✅ Tayyor")
    builder.adjust(1)
    return builder.as_markup(resize_keyboard=True)


def edit_list_kb(students):
    """Kiritilgan o'quvchilar ro'yxati — tanlab tuzatish/o'chirish uchun."""
    builder = InlineKeyboardBuilder()
    for i, s in enumerate(students):
        percent = s.get("percent", 0)
        builder.button(
            text=f"{s['surname']} {s['name']} — {percent:.1f}%",
            callback_data=f"edit_pick:{i}",
        )
    builder.button(text="◀️ Orqaga", callback_data="edit_cancel")
    builder.adjust(1)
    return builder.as_markup()


def edit_action_kb(index: int):
    builder = InlineKeyboardBuilder()
    builder.button(text="✏️ Balini tuzatish", callback_data=f"edit_score:{index}")
    builder.button(text="🗑 O'chirish", callback_data=f"edit_delete:{index}")
    builder.button(text="◀️ Orqaga", callback_data="edit_list_back")
    builder.adjust(1)
    return builder.as_markup()


def entry_mode_kb(saved_count: int = 0):
    builder = InlineKeyboardBuilder()
    if saved_count:
        builder.button(
            text=f"📂 Saqlangan ro'yxatdan foydalanish ({saved_count} ta)",
            callback_data="entry_mode:saved",
        )
        builder.button(
            text="🗑 Guruhdan o'quvchi o'chirish",
            callback_data="entry_mode:manage",
        )
    builder.button(text="📋 Ro'yxatni bir xabarda yuborish (tezroq)", callback_data="entry_mode:bulk")
    builder.button(text="📝 Birma-bir kiritish", callback_data="entry_mode:single")
    builder.adjust(1)
    return builder.as_markup()


def manage_group_kb(students, selected):
    """selected = GURUHDAN O'CHIRILADIGAN (belgilangan) o'quvchilar to'plami."""
    builder = InlineKeyboardBuilder()
    for i, s in enumerate(students):
        mark = "🗑" if i in selected else "⬜️"
        builder.button(
            text=f"{mark} {s['surname']} {s['name']}", callback_data=f"manage_toggle:{i}"
        )
    builder.button(text="✅ Belgilanganlarni o'chirish", callback_data="manage_confirm")
    builder.button(text="◀️ Orqaga", callback_data="manage_back")
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

def role_choice_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="👩‍🏫 Men Ustozman", callback_data="role:TEACHER")
    builder.button(text="🧑‍💼 Men Examinerman", callback_data="role:EXAMINER")
    builder.button(text="🏫 O'quv bo'lim rahbariman", callback_data="role:STUDY_HEAD")
    builder.button(text="🛠 Adminman", callback_data="role:ADMIN")
    builder.adjust(1)
    return builder.as_markup()


def branch_kb(branches, prefix="branch", exclude=None):
    exclude = exclude or []
    builder = InlineKeyboardBuilder()
    for b in branches:
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


def test_type_booking_kb(test_types):
    builder = InlineKeyboardBuilder()
    for t in test_types:
        builder.button(text=f"📘 {t}", callback_data=f"booking_type:{t}")
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
        builder.button(text="🔁 avval imtihon topshirgan guruh")
        builder.button(text="📋 Mening buyurtmalarim")
        builder.button(text="➕ Filial qo'shish")
    elif role == "EXAMINER":
        builder.button(text="🆕 Test kiritish")
        builder.button(text="📅 Mening imtihonlarim")
    elif role == "STUDY_HEAD":
        builder.button(text="ℹ️ Yordam")
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


REPEAT_FIELD_LABELS = {
    "branch": "🏢 Filial",
    "exam_date": "📅 Sana",
    "exam_time": "🕒 Vaqt",
    "test_type": "📘 Test turi",
    "students_count": "👥 O'quvchilar soni",
}
REPEAT_FIELD_ORDER = ["branch", "exam_date", "exam_time", "test_type", "students_count"]


def repeat_fields_kb(selected: set):
    """selected = qayta SO'RALADIGAN (belgilangan) maydonlar to'plami; qolganlari avtomatik to'ldiriladi."""
    builder = InlineKeyboardBuilder()
    for key in REPEAT_FIELD_ORDER:
        mark = "☑️" if key in selected else "⬜️"
        builder.button(
            text=f"{mark} {REPEAT_FIELD_LABELS[key]}", callback_data=f"repeat_toggle:{key}"
        )
    builder.button(text="▶️ Davom etish", callback_data="repeat_start")
    builder.button(text="❌ Bekor qilish", callback_data="repeat_cancel")
    builder.adjust(1)
    return builder.as_markup()


def admin_panel_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="📋 Kutilayotgan examinerlar", callback_data="admin_pending")
    builder.button(text="📅 Faol buyurtmalar", callback_data="admin_bookings")
    builder.button(text="🔍 Qidiruv", callback_data="admin_search")
    builder.button(text="📈 Statistika (30 kun)", callback_data="admin_stats")
    builder.button(text="👤 Xodimlar (o'chirish)", callback_data="admin_staff")
    builder.button(text="🏢 Filiallarni boshqarish", callback_data="admin_branches")
    builder.button(text="🧪 Test turlarini boshqarish", callback_data="admin_test_types")
    builder.button(text="🎯 Baholash chegaralari", callback_data="admin_grading")
    builder.button(text="📝 Buyurtma maydonlari", callback_data="admin_booking_fields")
    builder.button(text="🛡 Adminlar ro'yxati", callback_data="admin_admins")
    builder.button(text="➕ Admin qo'shish", callback_data="admin_add")
    builder.button(text="🏫 O'quv bo'lim rahbari ruxsatlari", callback_data="admin_study_heads")
    builder.button(text="➕ O'quv bo'lim rahbari qo'shish", callback_data="admin_add_study_head")
    builder.button(text="📊 Kunlik hisobot (hozir)", callback_data="admin_daily_report")
    builder.button(text="📥 Bazani hoziroq yuklab olish", callback_data="admin_backup")
    builder.button(text="⏰ Eslatma vaqti", callback_data="admin_reminder_setting")
    builder.button(text="ℹ️ Admin guruh sozlash", callback_data="admin_group_info")
    builder.adjust(1)
    return builder.as_markup()


def branch_manage_kb(branches):
    builder = InlineKeyboardBuilder()
    for b in branches:
        builder.button(text=f"🗑 {b}", callback_data=f"branch_del:{b}")
    builder.button(text="➕ Yangi filial qo'shish", callback_data="branch_add")
    builder.adjust(1)
    return builder.as_markup()


def branch_delete_confirm_kb(name: str):
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Ha, o'chirish", callback_data=f"branch_del_yes:{name}")
    builder.button(text="❌ Bekor qilish", callback_data="branch_del_no")
    builder.adjust(2)
    return builder.as_markup()


def test_type_manage_kb(test_types):
    builder = InlineKeyboardBuilder()
    for t in test_types:
        builder.button(text=f"🗑 {t}", callback_data=f"testtype_del:{t}")
    builder.button(text="➕ Yangi test turi qo'shish", callback_data="testtype_add")
    builder.adjust(1)
    return builder.as_markup()


def test_type_delete_confirm_kb(name: str):
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Ha, o'chirish", callback_data=f"testtype_del_yes:{name}")
    builder.button(text="❌ Bekor qilish", callback_data="testtype_del_no")
    builder.adjust(2)
    return builder.as_markup()


GRADING_LABELS = {
    "unit_excellent": "🏆 EXCELLENT chegarasi (UNIT)",
    "unit_good": "🥈 GOOD chegarasi (UNIT)",
    "unit_average": "🥉 AVERAGE chegarasi (UNIT)",
    "unit_bad": "⚠️ BAD chegarasi (UNIT, bundan past — FAIL)",
    "midterm_pass": "✅ PASS chegarasi (MIDTERM)",
}
GRADING_ORDER = ["unit_excellent", "unit_good", "unit_average", "unit_bad", "midterm_pass"]


def grading_thresholds_kb(thresholds: dict):
    builder = InlineKeyboardBuilder()
    for key in GRADING_ORDER:
        builder.button(
            text=f"{GRADING_LABELS[key]}: {thresholds[key]}%",
            callback_data=f"grading_edit:{key}",
        )
    builder.adjust(1)
    return builder.as_markup()


def booking_field_manage_kb(fields):
    builder = InlineKeyboardBuilder()
    for f in fields:
        builder.button(text=f"🗑 {f['label']}", callback_data=f"bookfield_del:{f['field_key']}")
    builder.button(text="➕ Yangi maydon qo'shish", callback_data="bookfield_add")
    builder.adjust(1)
    return builder.as_markup()


def booking_field_delete_confirm_kb(field_key: str):
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Ha, o'chirish", callback_data=f"bookfield_del_yes:{field_key}")
    builder.button(text="❌ Bekor qilish", callback_data="bookfield_del_no")
    builder.adjust(2)
    return builder.as_markup()
