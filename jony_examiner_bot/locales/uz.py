"""O'zbek tili tarjimalari.

Yangi kalit qo'shsangiz, xuddi shu kalitni ru.py fayliga (va kelajakda
qo'shiladigan boshqa tillar fayllariga) ham qo'shishni unutmang — aks
holda o'sha tilda foydalanuvchi standart (uz) matnni ko'radi.

Bu fayl hozircha "skelet" bosqichida — asosiy kalitlar keyingi
bosqichlarda (registration.py, booking.py, exam_flow.py, admin.py
matnlari o'girilganda) shu yerga qo'shib boriladi.
"""

TRANSLATIONS = {
    "language_name": "O'zbekcha",
    "choose_language": "Tilni tanlang:",
    "language_changed": "✅ Til o'zbek tiliga o'zgartirildi.",
    "change_language_button": "🌐 Tilni o'zgartirish",

    # ---- 3-bosqich: registration.py / start.py ----
    "reg_removed_account": "Sizning hisobingiz admin tomonidan o'chirilgan. Savol uchun admin bilan bog'laning.",
    "reg_teacher_welcome": (
        "Xush kelibsiz, {name}! ({branch} filiali)\n\n"
        "Imtihon buyurtma qilish uchun tugmani bosing.\n"
        "(Rolni o'zgartirish: /change_role)"
    ),
    "reg_examiner_rejected": "Afsuski, so'rovingiz rad etilgan. Admin bilan bog'laning.",
    "reg_examiner_welcome": (
        "Xush kelibsiz, {name}! ({branch} filiali, Examiner)\n\n"
        "Test natijalarini kiritish uchun tugmani bosing. Sizga mos filialdagi "
        "yangi imtihon buyurtmalari haqida ham shu yerda xabar beriladi.\n"
        "(Rolni o'zgartirish: /change_role)"
    ),
    "role_choice_prompt": (
        "Assalomu alaykum! 👋\n<b>Jony Academy Bot</b>ga xush kelibsiz.\n\n"
        "Avval ro'yxatdan o'tamiz. Siz kimsiz?"
    ),
    "role_btn_teacher": "👩‍🏫 Men Ustozman",
    "role_btn_examiner": "🧑‍💼 Men Examinerman",
    "change_role_prompt": "Rolingizni tanlang:",
    "reg_ask_full_name": "Ism va familiyangizni kiriting:",
    "reg_ask_branch": "Filialingizni tanlang:",
    "reg_done": "Ro'yxatdan o'tdingiz ✅\nFilial: {branch}",
    "reg_teacher_book_hint": "Imtihon buyurtma qilish uchun tugmani bosing:",
    "reg_examiner_enter_hint": "Test natijalarini kiritish uchun tugmani bosing:",
    "menu_add_branch": "➕ Filial qo'shish",
    "add_branch_already_all": "Siz allaqachon barcha filiallarga qo'shilgansiz.",
    "add_branch_choose": "Qaysi filialni qo'shmoqchisiz?",
    "add_branch_added": "✅ {branch} filiali qo'shildi.",
    "examiner_approved_msg": "Tabriklaymiz! So'rovingiz tasdiqlandi ✅\n\nEndi /start bosing.",
    "examiner_rejected_msg": "Afsuski, so'rovingiz rad etildi. Admin bilan bog'laning.",
    "whoami_not_registered": "Siz hali ro'yxatdan o'tmagansiz. /start bosing.",
    "whoami_info": "Ism: {name}\nRol: {role}\nFilial: {branch}{branches}\nHolat: {status}",
    "whoami_branches": "\nFiliallar: {list}",
}
