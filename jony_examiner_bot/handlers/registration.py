from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

import database as db
from states import RegStates
from keyboards import (
    language_choice_kb,
    role_choice_kb,
    branch_kb,
    build_main_menu_kb,
    admin_only_menu_kb,
    admin_panel_kb,
)
from locales import LANGUAGES, t

router = Router()

# Ba'zi tugmalar reply-keyboard bo'lgani uchun (F.text == ...) matn orqali
# aniqlanadi. Til tanlanganda matn o'zgargani sabab, shu tugmalar uchun
# BARCHA tilardagi variantlarni bitta to'plamga yig'ib, filter shu to'plam
# bilan solishtiriladi.
CHANGE_LANGUAGE_LABELS = {t("change_language_button", code) for code in LANGUAGES}
ADD_BRANCH_LABELS = {t("menu_add_branch", code) for code in LANGUAGES}


async def send_menu_for_user(answer_func, telegram_id: int, user: dict):
    is_adm = await db.is_admin(telegram_id)
    lang = await db.get_user_language(telegram_id)
    if user["role"] == "TEACHER":
        await answer_func(
            t("reg_teacher_welcome", lang, name=user["full_name"], branch=user["branch"]),
            reply_markup=build_main_menu_kb("TEACHER", is_adm, lang),
        )
    elif user["role"] == "EXAMINER":
        if user["status"] == "rejected":
            await answer_func(t("reg_examiner_rejected", lang))
            return
        await answer_func(
            t("reg_examiner_welcome", lang, name=user["full_name"], branch=user["branch"]),
            reply_markup=build_main_menu_kb("EXAMINER", is_adm, lang),
        )


async def _prompt_role_or_admin(answer_func, telegram_id: int, state: FSMContext):
    """Til tanlangandan keyin (yoki allaqachon tanlangan bo'lsa) davom etadigan qism:
    admin bo'lsa — admin xush kelibsiz xabari, bo'lmasa — rol tanlash oqimi.

    Eslatma: admin xush kelibsiz xabari va admin panel hozircha o'zbekcha
    qoladi (admin.py bilan birga 6-bosqichda qaraladi)."""
    is_adm = await db.is_admin(telegram_id)
    lang = await db.get_user_language(telegram_id)
    if is_adm:
        await answer_func(
            "👋 Siz <b>ADMIN</b> sifatida belgilangansiz!\n\n"
            "Pastdagi tugma orqali admin panelga kirishingiz mumkin.\n\n"
            "Agar bundan tashqari Ustoz yoki Examiner sifatida ham ro'yxatdan "
            "o'tmoqchi bo'lsangiz, /change_role yozing.",
            reply_markup=admin_only_menu_kb(lang),
        )
        return

    await state.set_state(RegStates.choose_role)
    await answer_func(
        t("role_choice_prompt", lang),
        reply_markup=role_choice_kb(lang),
    )


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    telegram_id = message.from_user.id
    user = await db.get_user(telegram_id)
    if user:
        if user["status"] == "removed":
            lang = await db.get_user_language(telegram_id)
            await message.answer(t("reg_removed_account", lang))
            return
        await send_menu_for_user(message.answer, telegram_id, user)
        return

    if not await db.has_language_pref(telegram_id):
        await state.set_state(RegStates.choose_language)
        await message.answer(
            "🌐 Tilni tanlang / Выберите язык:",
            reply_markup=language_choice_kb(),
        )
        return

    await _prompt_role_or_admin(message.answer, telegram_id, state)


@router.callback_query(F.data.startswith("setlang:"))
async def set_language_cb(callback: CallbackQuery, state: FSMContext):
    lang = callback.data.split(":", 1)[1]
    telegram_id = callback.from_user.id
    ok = await db.set_user_language(telegram_id, lang)
    if not ok:
        await callback.answer("Noma'lum til.", show_alert=True)
        return

    label = LANGUAGES.get(lang, lang)
    await callback.message.edit_text(f"✅ {label}")

    current_state = await state.get_state()
    if current_state == RegStates.choose_language.state:
        # Ro'yxatdan o'tishning birinchi qadami sifatida til tanlangan edi — davom etamiz
        await state.clear()
        await _prompt_role_or_admin(callback.message.answer, telegram_id, state)
    else:
        # Mavjud foydalanuvchi/admin tilni asosiy menyudan o'zgartirdi — menyuni qayta ko'rsatamiz
        user = await db.get_user(telegram_id)
        if user:
            await send_menu_for_user(callback.message.answer, telegram_id, user)
        elif await db.is_admin(telegram_id):
            await callback.message.answer("Admin panel:", reply_markup=admin_only_menu_kb(lang))
    await callback.answer()


@router.message(F.text.in_(CHANGE_LANGUAGE_LABELS))
async def change_language_button(message: Message):
    await message.answer(
        "Tilni tanlang / Выберите язык:",
        reply_markup=language_choice_kb(),
    )


@router.message(Command("change_role"))
async def change_role(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(RegStates.choose_role)
    lang = await db.get_user_language(message.from_user.id)
    await message.answer(
        t("change_role_prompt", lang),
        reply_markup=role_choice_kb(lang),
    )


@router.message(F.text == "🛠 Admin panel")
async def admin_panel_button(message: Message):
    if not await db.is_admin(message.from_user.id):
        await message.answer("Siz admin emassiz.")
        return
    await message.answer("🛠 <b>Admin panel</b>", reply_markup=admin_panel_kb())


@router.callback_query(RegStates.choose_role, F.data.startswith("role:"))
async def choose_role(callback: CallbackQuery, state: FSMContext):
    role = callback.data.split(":")[1]
    lang = await db.get_user_language(callback.from_user.id)

    if role == "ADMIN":
        await state.clear()
        is_adm = await db.is_admin(callback.from_user.id)
        if is_adm:
            await callback.message.edit_text("🛠 Siz admin ekansiz.")
            await callback.message.answer("Admin panel:", reply_markup=admin_panel_kb())
        else:
            await callback.message.edit_text(
                "Siz hali admin emassiz. Admin bo'lish uchun mavjud admin sizni "
                "/add_admin orqali qo'shishi kerak."
            )
        await callback.answer()
        return

    await state.update_data(role=role)
    await state.set_state(RegStates.full_name)
    await callback.message.edit_text(t("reg_ask_full_name", lang))
    await callback.answer()


@router.message(RegStates.full_name)
async def get_full_name(message: Message, state: FSMContext):
    await state.update_data(full_name=message.text)
    await state.set_state(RegStates.choose_branch)
    branches = await db.get_branches()
    lang = await db.get_user_language(message.from_user.id)
    await message.answer(t("reg_ask_branch", lang), reply_markup=branch_kb(branches))


@router.callback_query(RegStates.choose_branch, F.data.startswith("branch:"))
async def choose_branch(callback: CallbackQuery, state: FSMContext):
    branch = callback.data.split(":", 1)[1]
    data = await state.get_data()
    role = data["role"]
    full_name = data["full_name"]
    telegram_id = callback.from_user.id
    username = callback.from_user.username
    lang = await db.get_user_language(telegram_id)

    # Endi ustoz ham, examiner ham darhol faol bo'ladi — admin tasdiqlash shart emas
    status = "active"
    await db.upsert_user(telegram_id, role, full_name, branch, status, username)
    if role == "TEACHER":
        await db.add_teacher_branch(telegram_id, branch)
    await state.clear()

    is_adm = await db.is_admin(telegram_id)

    if role == "TEACHER":
        await callback.message.edit_text(t("reg_done", lang, branch=branch))
        await callback.message.answer(
            t("reg_teacher_book_hint", lang),
            reply_markup=build_main_menu_kb("TEACHER", is_adm, lang),
        )
    else:
        await callback.message.edit_text(t("reg_done", lang, branch=branch))
        await callback.message.answer(
            t("reg_examiner_enter_hint", lang),
            reply_markup=build_main_menu_kb("EXAMINER", is_adm, lang),
        )
        # Bu bildirishnoma admin guruhga boradi (shaxsiy foydalanuvchi tiliga bog'liq
        # emas), shuning uchun hozircha o'zbekcha qoladi — admin.py bilan 6-bosqichda.
        admin_group_id = await db.get_setting("admin_group_id")
        if admin_group_id:
            uname = f"@{username}" if username else "username yo'q"
            try:
                await callback.bot.send_message(
                    int(admin_group_id),
                    f"ℹ️ Yangi Examiner ro'yxatdan o'tdi\n\n"
                    f"Ism: {full_name}\nFilial: {branch}\nTelegram: {uname}",
                )
            except Exception:
                pass
    await callback.answer()


# ---------- FILIAL QO'SHISH (ustoz bir nechta filialda ishlashi uchun) ----------

@router.message(F.text.in_(ADD_BRANCH_LABELS))
async def add_branch_start(message: Message):
    user = await db.get_user(message.from_user.id)
    if not user or user["role"] != "TEACHER":
        return
    lang = await db.get_user_language(message.from_user.id)
    all_branches = await db.get_branches()
    existing = await db.get_teacher_branches(message.from_user.id)
    if len(existing) >= len(all_branches):
        await message.answer(t("add_branch_already_all", lang))
        return
    await message.answer(
        t("add_branch_choose", lang),
        reply_markup=branch_kb(all_branches, prefix="addbranch", exclude=existing),
    )


@router.callback_query(F.data.startswith("addbranch:"))
async def add_branch_confirm(callback: CallbackQuery):
    branch = callback.data.split(":", 1)[1]
    lang = await db.get_user_language(callback.from_user.id)
    await db.add_teacher_branch(callback.from_user.id, branch)
    await callback.message.edit_text(t("add_branch_added", lang, branch=branch))
    await callback.answer()


# ---------- ADMIN PANEL TUGMALARI (callback) ----------

@router.callback_query(F.data == "admin_group_info")
async def admin_group_info(callback: CallbackQuery):
    await callback.message.answer(
        "Admin guruhni belgilash uchun:\n"
        "1. Botni kerakli guruhga qo'shing\n"
        "2. O'sha guruhda <code>/admin_group</code> deb yozing\n\n"
        "(Bu faqat guruh ichida ishlaydi, shaxsiy chatda emas)"
    )
    await callback.answer()


# ---------- ESKI (endi ishlatilmaydi, lekin eski pending yozuvlar uchun qoldirilgan) ----------

@router.callback_query(F.data.startswith("approve_examiner:"))
async def approve_examiner(callback: CallbackQuery):
    if not await db.is_admin(callback.from_user.id):
        await callback.answer("Bu tugma faqat adminlar uchun.", show_alert=True)
        return
    telegram_id = int(callback.data.split(":")[1])
    await db.update_user_status(telegram_id, "active")
    try:
        await callback.message.edit_text(callback.message.text + "\n\n✅ TASDIQLANDI")
    except Exception:
        pass
    try:
        target_lang = await db.get_user_language(telegram_id)
        await callback.bot.send_message(
            telegram_id,
            t("examiner_approved_msg", target_lang),
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
    try:
        await callback.message.edit_text(callback.message.text + "\n\n❌ RAD ETILDI")
    except Exception:
        pass
    try:
        target_lang = await db.get_user_language(telegram_id)
        await callback.bot.send_message(telegram_id, t("examiner_rejected_msg", target_lang))
    except Exception:
        pass
    await callback.answer("Rad etildi")


@router.message(Command("whoami"))
async def whoami(message: Message):
    user = await db.get_user(message.from_user.id)
    is_adm = await db.is_admin(message.from_user.id)
    lang = await db.get_user_language(message.from_user.id)
    if not user and not is_adm:
        await message.answer(t("whoami_not_registered", lang))
        return
    lines = []
    if user:
        branches = await db.get_teacher_branches(message.from_user.id) if user["role"] == "TEACHER" else []
        branch_text = t("whoami_branches", lang, list=", ".join(branches)) if branches else ""
        lines.append(
            t(
                "whoami_info", lang,
                name=user["full_name"], role=user["role"],
                branch=user["branch"], branches=branch_text, status=user["status"],
            )
        )
    if is_adm:
        lines.append("🛠 Siz ADMIN sifatida ham belgilangansiz.")
    await message.answer("\n\n".join(lines))
