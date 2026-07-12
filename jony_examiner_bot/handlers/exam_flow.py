import os
from datetime import datetime

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.fsm.context import FSMContext

from states import ExamStates
from keyboards import (
    test_type_kb,
    sections_confirm_kb,
    after_student_kb,
    cancel_kb,
    build_main_menu_kb,
    entry_mode_kb,
    retake_checkbox_kb,
    manage_group_kb,
    edit_list_kb,
    edit_action_kb,
    accept_booking_kb,
)
from excel_export import build_excel

import database as db

router = Router()

DEFAULT_SECTIONS = {"listening": 20, "reading": 25, "writing": 40, "speaking": 15}


# ---------- STATUS HISOBLASH ----------

def unit_status(percent: float) -> str:
    if percent >= 95:
        return "EXCELLENT"
    if percent >= 84:
        return "GOOD"
    if percent >= 73:
        return "AVERAGE"
    if percent >= 64:
        return "BAD"
    return "FAIL"


def midterm_status(percent: float) -> str:
    return "PASS" if percent >= 60 else "FAIL"


async def safe_float(text: str):
    try:
        return float(text.replace(",", "."))
    except ValueError:
        return None


async def _prepare_entry_mode(state: FSMContext, telegram_id: int) -> int:
    """Guruh nomi bo'yicha saqlangan o'quvchilar ro'yxatini tekshiradi va
    state'ga joylab, topilgan sonini qaytaradi (entry_mode_kb uchun)."""
    data = await state.get_data()
    user = await db.get_user(telegram_id)
    branch = user["branch"] if user else None
    group_name = data.get("level_name", "")
    saved = await db.get_saved_group_students(branch, group_name) if branch else []
    await state.update_data(saved_students_available=saved, saved_branch=branch)
    return len(saved)


async def _advance_saved_queue(target, state: FSMContext):
    """Saqlangan ro'yxatdagi keyingi o'quvchini navbatdan olib, to'g'ridan-to'g'ri
    ball kiritish bosqichiga o'tkazadi (ism-familiya qayta so'ralmaydi)."""
    data = await state.get_data()
    queue = list(data.get("saved_queue", []))
    nxt = queue.pop(0)
    await state.update_data(saved_queue=queue, cur_surname=nxt["surname"], cur_name=nxt["name"])
    if data["test_type"] == "unit":
        await state.set_state(ExamStates.student_score_unit)
        await target.answer(
            f"👤 {nxt['surname']} {nxt['name']} — ball nechi? (max {data['max_score']}):"
        )
    else:
        await state.set_state(ExamStates.student_score_listening)
        sec = data["sections"]
        await target.answer(
            f"👤 {nxt['surname']} {nxt['name']} — LISTENING ball (max {sec['listening']}):"
        )


# ---------- BOSHLASH ----------

@router.message(F.text == "🆕 Test kiritish")
async def start_exam(message: Message, state: FSMContext):
    user = await db.get_user(message.from_user.id)
    if not user or user["role"] != "EXAMINER" or user["status"] not in ("active", "approved"):
        await message.answer("Bu funksiya faqat tasdiqlangan Examinerlar uchun.")
        return
    await state.clear()
    await state.set_state(ExamStates.teacher)
    await message.answer(
        "📋 Yangi test kiritish boshlandi.\n\nO'qituvchi ismini kiriting (TEACHER):",
        reply_markup=cancel_kb(),
    )


@router.message(F.text == "❌ Bekor qilish")
async def cancel_flow(message: Message, state: FSMContext):
    await state.clear()
    is_adm = await db.is_admin(message.from_user.id)
    await message.answer("Bekor qilindi.", reply_markup=build_main_menu_kb("EXAMINER", is_adm))


# ---------- MENING IMTIHONLARIM ----------

@router.message(F.text == "📅 Mening imtihonlarim")
async def my_schedule(message: Message):
    user = await db.get_user(message.from_user.id)
    if not user or user["role"] != "EXAMINER" or user["status"] == "removed":
        return
    bookings = await db.get_examiner_upcoming_bookings(message.from_user.id)
    if not bookings:
        await message.answer("Sizda hozircha qabul qilingan (kelayotgan) imtihonlar yo'q.")
        return

    lines = ["📅 <b>Mening imtihonlarim:</b>"]
    for b in bookings:
        test_info = b["test_type"]
        if b.get("test_name"):
            test_info += f" ({b['test_name']})"
        lines.append(
            f"\n🟢 <b>{b['exam_date']} {b['exam_time']}</b> — {b['branch']}\n"
            f"Ustoz: {b['teacher_name']}\nGuruh: {b['group_name']}\n"
            f"Turi: {test_info}\nO'quvchilar soni: {b['students_count']}"
        )
    await message.answer("\n".join(lines))


# ---------- KUTILAYOTGAN BUYURTMALAR (o'tkazib yuborilgan / hali qabul qilinmagan) ----------

@router.message(F.text == "🕓 Kutilayotgan buyurtmalar")
async def pending_orders(message: Message):
    user = await db.get_user(message.from_user.id)
    if not user or user["role"] != "EXAMINER" or user["status"] not in ("active", "approved"):
        await message.answer("Bu funksiya faqat tasdiqlangan Examinerlar uchun.")
        return

    branches = await db.get_user_all_branches(message.from_user.id, user["branch"])
    if not branches:
        branches = [user["branch"]]

    seen_ids = set()
    bookings = []
    for br in branches:
        for b in await db.get_pending_bookings_by_branch(br):
            if b["id"] not in seen_ids:
                seen_ids.add(b["id"])
                bookings.append(b)

    if not bookings:
        await message.answer("Hozircha kutilayotgan (qabul qilinmagan) buyurtmalar yo'q.")
        return

    await message.answer(
        f"🕓 <b>{', '.join(branches)}</b> filial(lar)i bo'yicha kutilayotgan buyurtmalar ({len(bookings)} ta):"
    )
    for b in bookings:
        test_info = b["test_type"]
        if b.get("test_name"):
            test_info += f" ({b['test_name']})"
        text = (
            f"🔔 <b>Imtihon buyurtmasi</b>\n\n"
            f"Ustoz: {b['teacher_name']}\n"
            f"Filial: {b['branch']}\n"
            f"Sana: {b['exam_date']}\n"
            f"Vaqt: {b['exam_time']}\n"
            f"Test turi: {test_info}\n"
            f"Guruh: {b['group_name']}\n"
            f"O'quvchilar soni: {b['students_count']}"
        )
        try:
            sent = await message.answer(text, reply_markup=accept_booking_kb(b["id"]))
            await db.add_notification(b["id"], sent.chat.id, sent.message_id)
        except Exception:
            pass


# ---------- HEADER MA'LUMOTLARI ----------

@router.message(ExamStates.teacher)
async def get_teacher(message: Message, state: FSMContext):
    await state.update_data(teacher=message.text)
    await state.set_state(ExamStates.date)
    await message.answer("Sana kiriting (DATE), masalan 07.07.2026:")


@router.message(ExamStates.date)
async def get_date(message: Message, state: FSMContext):
    await state.update_data(date=message.text)
    await state.set_state(ExamStates.level)
    await message.answer("Daraja (LEVEL) kiriting, masalan STEP 1.0:")


@router.message(ExamStates.level)
async def get_level(message: Message, state: FSMContext):
    await state.update_data(level=message.text)
    await state.set_state(ExamStates.study_dates)
    await message.answer("O'qish kunlari va vaqti (STUDY DATES AND TIMES), masalan EVEN DAYS 8:00:")


@router.message(ExamStates.study_dates)
async def get_study_dates(message: Message, state: FSMContext):
    await state.update_data(study_dates=message.text)
    await state.set_state(ExamStates.examiner)
    await message.answer("Examiner ismini kiriting:")


@router.message(ExamStates.examiner)
async def get_examiner(message: Message, state: FSMContext):
    await state.update_data(examiner=message.text)
    await state.set_state(ExamStates.test_type)
    await message.answer("Test turini tanlang:", reply_markup=test_type_kb())


# ---------- TEST TURI ----------

@router.callback_query(ExamStates.test_type, F.data == "test_type:unit")
async def choose_unit(callback: CallbackQuery, state: FSMContext):
    await state.update_data(test_type="unit", students=[])
    await state.set_state(ExamStates.unit_name)
    await callback.message.edit_text("Test nomini kiriting (masalan: UNIT 3):")
    await callback.answer()


@router.callback_query(ExamStates.test_type, F.data == "test_type:midterm")
async def choose_midterm(callback: CallbackQuery, state: FSMContext):
    await state.update_data(test_type="midterm", students=[])
    await state.set_state(ExamStates.midterm_name)
    await callback.message.edit_text("Test nomini kiriting (masalan: MIDTERM yoki END OF COURSE):")
    await callback.answer()


# ---------- UNIT TEST QO'SHIMCHA MA'LUMOTLARI ----------

@router.message(ExamStates.unit_name)
async def get_unit_name(message: Message, state: FSMContext):
    await state.update_data(test_name=message.text)
    await state.set_state(ExamStates.unit_level_name)
    await message.answer("Guruh nomini kiriting (masalan: NOVA yoki Bornleaders25):")


@router.message(ExamStates.unit_level_name)
async def get_unit_level_name(message: Message, state: FSMContext):
    await state.update_data(level_name=message.text)
    await state.set_state(ExamStates.unit_max_score)
    await message.answer("Maksimal ball necha? (masalan: 30):")


@router.message(ExamStates.unit_max_score)
async def get_unit_max_score(message: Message, state: FSMContext):
    val = await safe_float(message.text)
    if val is None:
        await message.answer("Iltimos, faqat son kiriting (masalan: 30):")
        return
    await state.update_data(max_score=val)
    saved_count = await _prepare_entry_mode(state, message.from_user.id)
    await state.set_state(ExamStates.entry_mode_choice)
    await message.answer(
        "O'quvchilarni qanday kiritmoqchisiz?", reply_markup=entry_mode_kb(saved_count)
    )


# ---------- MIDTERM QO'SHIMCHA MA'LUMOTLARI ----------

@router.message(ExamStates.midterm_name)
async def get_midterm_name(message: Message, state: FSMContext):
    await state.update_data(test_name=message.text)
    await state.set_state(ExamStates.midterm_level_name)
    await message.answer("Guruh nomini kiriting (masalan: PRIME yoki Bornleaders25):")


@router.message(ExamStates.midterm_level_name)
async def get_midterm_level_name(message: Message, state: FSMContext):
    await state.update_data(level_name=message.text)
    await state.set_state(ExamStates.sections_confirm)
    await message.answer(
        "Bo'limlar bo'yicha maksimal ballar:\n"
        "LISTENING: 20\nREADING: 25\nWRITING: 40\nSPEAKING: 15\n(Jami: 100)\n\n"
        "Shu standart bo'yicha davom etamizmi?",
        reply_markup=sections_confirm_kb(),
    )


@router.callback_query(ExamStates.sections_confirm, F.data == "sections:default")
async def sections_default(callback: CallbackQuery, state: FSMContext):
    await state.update_data(sections=dict(DEFAULT_SECTIONS))
    saved_count = await _prepare_entry_mode(state, callback.from_user.id)
    await state.set_state(ExamStates.entry_mode_choice)
    await callback.message.edit_text("Standart ballar qabul qilindi ✅")
    await callback.message.answer(
        "O'quvchilarni qanday kiritmoqchisiz?", reply_markup=entry_mode_kb(saved_count)
    )
    await callback.answer()


@router.callback_query(ExamStates.sections_confirm, F.data == "sections:edit")
async def sections_edit_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(ExamStates.sections_edit_listening)
    await callback.message.edit_text("LISTENING uchun max ball nechi?")
    await callback.answer()


@router.message(ExamStates.sections_edit_listening)
async def sec_listening(message: Message, state: FSMContext):
    val = await safe_float(message.text)
    if val is None:
        await message.answer("Faqat son kiriting:")
        return
    await state.update_data(sec_listening=val)
    await state.set_state(ExamStates.sections_edit_reading)
    await message.answer("READING uchun max ball nechi?")


@router.message(ExamStates.sections_edit_reading)
async def sec_reading(message: Message, state: FSMContext):
    val = await safe_float(message.text)
    if val is None:
        await message.answer("Faqat son kiriting:")
        return
    await state.update_data(sec_reading=val)
    await state.set_state(ExamStates.sections_edit_writing)
    await message.answer("WRITING uchun max ball nechi?")


@router.message(ExamStates.sections_edit_writing)
async def sec_writing(message: Message, state: FSMContext):
    val = await safe_float(message.text)
    if val is None:
        await message.answer("Faqat son kiriting:")
        return
    await state.update_data(sec_writing=val)
    await state.set_state(ExamStates.sections_edit_speaking)
    await message.answer("SPEAKING uchun max ball nechi?")


@router.message(ExamStates.sections_edit_speaking)
async def sec_speaking(message: Message, state: FSMContext):
    val = await safe_float(message.text)
    if val is None:
        await message.answer("Faqat son kiriting:")
        return
    data = await state.get_data()
    sections = {
        "listening": data["sec_listening"],
        "reading": data["sec_reading"],
        "writing": data["sec_writing"],
        "speaking": val,
    }
    await state.update_data(sections=sections)
    saved_count = await _prepare_entry_mode(state, message.from_user.id)
    await state.set_state(ExamStates.entry_mode_choice)
    await message.answer(
        "Ballar saqlandi ✅\n\nO'quvchilarni qanday kiritmoqchisiz?",
        reply_markup=entry_mode_kb(saved_count),
    )


# ---------- KIRITISH REJIMI TANLASH ----------

@router.callback_query(ExamStates.entry_mode_choice, F.data == "entry_mode:single")
async def entry_mode_single(callback: CallbackQuery, state: FSMContext):
    await state.set_state(ExamStates.student_surname)
    await callback.message.edit_text("1-o'quvchining FAMILIYASI:")
    await callback.answer()


@router.callback_query(ExamStates.entry_mode_choice, F.data == "entry_mode:bulk")
async def entry_mode_bulk(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await state.set_state(ExamStates.bulk_entry)
    if data["test_type"] == "unit":
        example = (
            "Har bir o'quvchini YANGI QATORDA yozing:\n"
            "<b>Familiya Ism Ball</b>\n\n"
            "Masalan:\n"
            "Alisherova Malika 30\n"
            "Yaxshiboyeva Gulsevar 28\n"
            "Nabiddinova Dilshoda 25\n\n"
            "(Excel'dan Familiya, Ism, Ball ustunlarini belgilab, nusxalab, "
            "shu yerga qo'yishingiz ham mumkin)"
        )
    else:
        example = (
            "Har bir o'quvchini YANGI QATORDA yozing:\n"
            "<b>Familiya Ism Listening Reading Writing Speaking</b>\n\n"
            "Masalan:\n"
            "Nematova Kumush 19 24 33 13\n"
            "Sarvarjonova Xadija 13 19 36 14\n\n"
            "(Excel'dan tegishli ustunlarni belgilab, nusxalab, shu yerga "
            "qo'yishingiz ham mumkin)"
        )
    await callback.message.edit_text(example)
    await callback.answer()


@router.callback_query(ExamStates.entry_mode_choice, F.data == "entry_mode:saved")
async def entry_mode_saved(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    saved = data.get("saved_students_available") or []
    if not saved:
        await callback.answer("Saqlangan ro'yxat topilmadi.", show_alert=True)
        return
    await state.update_data(saved_queue=list(saved), students=[])
    await callback.message.edit_text(f"📂 Saqlangan ro'yxatdan {len(saved)} ta o'quvchi yuklandi.")
    await _advance_saved_queue(callback.message, state)
    await callback.answer()


# ---------- SAQLANGAN GURUHDAN O'QUVCHINI O'CHIRISH ----------

@router.callback_query(ExamStates.entry_mode_choice, F.data == "entry_mode:manage")
async def entry_mode_manage(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    saved = data.get("saved_students_available") or []
    if not saved:
        await callback.answer("Saqlangan ro'yxat topilmadi.", show_alert=True)
        return
    await state.update_data(manage_selected=[])
    await state.set_state(ExamStates.manage_group_marking)
    await callback.message.edit_text(
        "Guruhdan qaysi o'quvchi(lar)ni O'CHIRMOQCHISIZ?\n\n"
        "🗑 belgilaganlaringiz keyingi safar bu guruh uchun taklif qilinmaydi.",
        reply_markup=manage_group_kb(saved, []),
    )
    await callback.answer()


@router.callback_query(ExamStates.manage_group_marking, F.data.startswith("manage_toggle:"))
async def manage_toggle(callback: CallbackQuery, state: FSMContext):
    idx = int(callback.data.split(":")[1])
    data = await state.get_data()
    selected = set(data.get("manage_selected", []))
    if idx in selected:
        selected.remove(idx)
    else:
        selected.add(idx)
    selected = list(selected)
    await state.update_data(manage_selected=selected)
    saved = data.get("saved_students_available") or []
    await callback.message.edit_reply_markup(reply_markup=manage_group_kb(saved, selected))
    await callback.answer()


@router.callback_query(ExamStates.manage_group_marking, F.data == "manage_back")
async def manage_back(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    saved_count = len(data.get("saved_students_available") or [])
    await state.set_state(ExamStates.entry_mode_choice)
    await callback.message.edit_text(
        "O'quvchilarni qanday kiritmoqchisiz?", reply_markup=entry_mode_kb(saved_count)
    )
    await callback.answer()


@router.callback_query(ExamStates.manage_group_marking, F.data == "manage_confirm")
async def manage_confirm(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected = data.get("manage_selected", [])
    saved = data.get("saved_students_available") or []
    branch = data.get("saved_branch")
    group_name = data.get("level_name", "")

    if not selected:
        await callback.answer("Hech kim belgilanmagan.", show_alert=True)
        return

    removed_names = [f"{saved[i]['surname']} {saved[i]['name']}" for i in selected]
    to_remove = [saved[i] for i in selected]
    remaining = await db.remove_students_from_group(branch, group_name, to_remove)
    await state.update_data(saved_students_available=remaining, manage_selected=[])

    text = "✅ Guruhdan o'chirildi:\n" + "\n".join(f"• {n}" for n in removed_names)
    text += f"\n\nGuruhda qoldi: {len(remaining)} ta o'quvchi."
    await callback.message.edit_text(text)

    await state.set_state(ExamStates.entry_mode_choice)
    await callback.message.answer(
        "O'quvchilarni qanday kiritmoqchisiz?", reply_markup=entry_mode_kb(len(remaining))
    )
    await callback.answer()


@router.message(ExamStates.bulk_entry)
async def bulk_entry_process(message: Message, state: FSMContext):
    data = await state.get_data()
    lines = [ln.strip() for ln in message.text.split("\n") if ln.strip()]
    students = data.get("students", [])
    added = 0
    errors = []

    for i, line in enumerate(lines, start=1):
        tokens = line.replace("\t", " ").split()
        try:
            if data["test_type"] == "unit":
                if len(tokens) < 3:
                    raise ValueError("kamida 3 ta qism kerak")
                surname = tokens[0]
                name = " ".join(tokens[1:-1])
                score = float(tokens[-1].replace(",", "."))
                if score < 0 or score > data["max_score"]:
                    raise ValueError(f"ball 0-{data['max_score']} oralig'ida bo'lishi kerak")
                percent = score / data["max_score"] * 100
                status = unit_status(percent)
                students.append({
                    "surname": surname, "name": name, "total": score,
                    "percent": percent, "status": status, "first_time": True,
                })
            else:
                if len(tokens) < 6:
                    raise ValueError("kamida 6 ta qism kerak")
                sec = data["sections"]
                surname = tokens[0]
                name = " ".join(tokens[1:-4])
                l, r, w, s = [float(t.replace(",", ".")) for t in tokens[-4:]]
                if not (0 <= l <= sec["listening"] and 0 <= r <= sec["reading"]
                        and 0 <= w <= sec["writing"] and 0 <= s <= sec["speaking"]):
                    raise ValueError("ballar max qiymatdan oshib ketgan")
                total = l + r + w + s
                max_total = sum(sec.values())
                percent = total / max_total * 100
                status = midterm_status(percent)
                students.append({
                    "surname": surname, "name": name, "listening": l, "reading": r,
                    "writing": w, "speaking": s, "total": total, "percent": percent,
                    "status": status, "first_time": True,
                })
            added += 1
        except Exception as e:
            errors.append(f"{i}-qator: \"{line}\" — {e}")

    await state.update_data(students=students)
    await state.set_state(ExamStates.after_student)

    msg = f"✅ {added} ta o'quvchi qo'shildi."
    if errors:
        msg += "\n\n⚠️ Quyidagi qatorlarda xatolik (qo'shilmadi):\n" + "\n".join(errors)
        msg += "\n\nBularni \"➕ O'quvchi qo'shish\" orqali birma-bir qo'shishingiz mumkin."
    await message.answer(msg, reply_markup=after_student_kb())


# ---------- O'QUVCHI KIRITISH (birma-bir) ----------

@router.message(ExamStates.student_surname)
async def get_student_surname(message: Message, state: FSMContext):
    await state.update_data(cur_surname=message.text)
    await state.set_state(ExamStates.student_name)
    await message.answer("Ismi:")


@router.message(ExamStates.student_name)
async def get_student_name(message: Message, state: FSMContext):
    data = await state.get_data()
    await state.update_data(cur_name=message.text)
    if data["test_type"] == "unit":
        await state.set_state(ExamStates.student_score_unit)
        await message.answer(f"Ball nechi? (max {data['max_score']}):")
    else:
        await state.set_state(ExamStates.student_score_listening)
        sec = data["sections"]
        await message.answer(f"LISTENING ball (max {sec['listening']}):")


@router.message(ExamStates.student_score_unit)
async def get_score_unit(message: Message, state: FSMContext):
    val = await safe_float(message.text)
    data = await state.get_data()
    if val is None or val < 0 or val > data["max_score"]:
        await message.answer(f"0 dan {data['max_score']}gacha son kiriting:")
        return

    percent = val / data["max_score"] * 100
    status = unit_status(percent)
    student = {
        "surname": data["cur_surname"],
        "name": data["cur_name"],
        "total": val,
        "percent": percent,
        "status": status,
        "first_time": True,
    }
    students = data.get("students", [])
    students.append(student)
    await state.update_data(students=students)
    await state.set_state(ExamStates.after_student)
    await message.answer(
        f"✅ {student['surname']} {student['name']} — {percent:.1f}% — {status}\n\nDavom etamizmi?",
        reply_markup=after_student_kb(),
    )


@router.message(ExamStates.student_score_listening)
async def get_score_listening(message: Message, state: FSMContext):
    data = await state.get_data()
    sec = data["sections"]
    val = await safe_float(message.text)
    if val is None or val < 0 or val > sec["listening"]:
        await message.answer(f"0 dan {sec['listening']}gacha son kiriting:")
        return
    await state.update_data(cur_listening=val)
    await state.set_state(ExamStates.student_score_reading)
    await message.answer(f"READING ball (max {sec['reading']}):")


@router.message(ExamStates.student_score_reading)
async def get_score_reading(message: Message, state: FSMContext):
    data = await state.get_data()
    sec = data["sections"]
    val = await safe_float(message.text)
    if val is None or val < 0 or val > sec["reading"]:
        await message.answer(f"0 dan {sec['reading']}gacha son kiriting:")
        return
    await state.update_data(cur_reading=val)
    await state.set_state(ExamStates.student_score_writing)
    await message.answer(f"WRITING ball (max {sec['writing']}):")


@router.message(ExamStates.student_score_writing)
async def get_score_writing(message: Message, state: FSMContext):
    data = await state.get_data()
    sec = data["sections"]
    val = await safe_float(message.text)
    if val is None or val < 0 or val > sec["writing"]:
        await message.answer(f"0 dan {sec['writing']}gacha son kiriting:")
        return
    await state.update_data(cur_writing=val)
    await state.set_state(ExamStates.student_score_speaking)
    await message.answer(f"SPEAKING ball (max {sec['speaking']}):")


@router.message(ExamStates.student_score_speaking)
async def get_score_speaking(message: Message, state: FSMContext):
    data = await state.get_data()
    sec = data["sections"]
    val = await safe_float(message.text)
    if val is None or val < 0 or val > sec["speaking"]:
        await message.answer(f"0 dan {sec['speaking']}gacha son kiriting:")
        return

    listening = data["cur_listening"]
    reading = data["cur_reading"]
    writing = data["cur_writing"]
    speaking = val
    total = listening + reading + writing + speaking
    max_total = sum(sec.values())
    percent = total / max_total * 100
    status = midterm_status(percent)

    student = {
        "surname": data["cur_surname"],
        "name": data["cur_name"],
        "listening": listening,
        "reading": reading,
        "writing": writing,
        "speaking": speaking,
        "total": total,
        "percent": percent,
        "status": status,
        "first_time": True,
    }
    students = data.get("students", [])
    students.append(student)
    await state.update_data(students=students)
    await state.set_state(ExamStates.after_student)
    await message.answer(
        f"✅ {student['surname']} {student['name']} — {percent:.1f}% — {status}\n\nDavom etamizmi?",
        reply_markup=after_student_kb(),
    )


@router.message(ExamStates.after_student, F.text == "➕ O'quvchi qo'shish")
async def add_more_student(message: Message, state: FSMContext):
    data = await state.get_data()
    if data.get("saved_queue"):
        await _advance_saved_queue(message, state)
    else:
        await state.set_state(ExamStates.student_surname)
        await message.answer("Keyingi o'quvchining FAMILIYASI:")


@router.message(ExamStates.after_student, F.text == "✏️ Tuzatish / O'chirish")
async def edit_menu_open(message: Message, state: FSMContext):
    data = await state.get_data()
    students = data.get("students", [])
    if not students:
        await message.answer("Hali hech qanday o'quvchi kiritilmagan.")
        return
    await state.set_state(ExamStates.edit_list)
    await message.answer(
        "Qaysi o'quvchini tuzatmoqchisiz yoki o'chirmoqchisiz?",
        reply_markup=edit_list_kb(students),
    )


@router.callback_query(ExamStates.edit_list, F.data == "edit_cancel")
async def edit_menu_cancel(callback: CallbackQuery, state: FSMContext):
    await state.set_state(ExamStates.after_student)
    await callback.message.edit_text("Bekor qilindi.")
    await callback.answer()


@router.callback_query(ExamStates.edit_list, F.data.startswith("edit_pick:"))
async def edit_pick_student(callback: CallbackQuery, state: FSMContext):
    idx = int(callback.data.split(":")[1])
    data = await state.get_data()
    students = data.get("students", [])
    if idx >= len(students):
        await callback.answer("O'quvchi topilmadi.", show_alert=True)
        return
    s = students[idx]
    await callback.message.edit_text(
        f"👤 {s['surname']} {s['name']} — {s['percent']:.1f}% ({s['status']})\n\n"
        "Nima qilmoqchisiz?",
        reply_markup=edit_action_kb(idx),
    )
    await callback.answer()


@router.callback_query(ExamStates.edit_list, F.data == "edit_list_back")
async def edit_list_back(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    students = data.get("students", [])
    if not students:
        await state.set_state(ExamStates.after_student)
        await callback.message.edit_text("O'quvchilar ro'yxati bo'sh qoldi.")
        await callback.answer()
        return
    await callback.message.edit_text(
        "Qaysi o'quvchini tuzatmoqchisiz yoki o'chirmoqchisiz?",
        reply_markup=edit_list_kb(students),
    )
    await callback.answer()


@router.callback_query(ExamStates.edit_list, F.data.startswith("edit_delete:"))
async def edit_delete_student(callback: CallbackQuery, state: FSMContext):
    idx = int(callback.data.split(":")[1])
    data = await state.get_data()
    students = data.get("students", [])
    if idx >= len(students):
        await callback.answer("O'quvchi topilmadi.", show_alert=True)
        return
    removed = students.pop(idx)
    await state.update_data(students=students)

    if not students:
        await state.set_state(ExamStates.after_student)
        await callback.message.edit_text(
            f"🗑 O'chirildi: {removed['surname']} {removed['name']}\n\n"
            "Ro'yxatda boshqa o'quvchi qolmadi."
        )
        await callback.answer()
        return

    await callback.message.edit_text(
        f"🗑 O'chirildi: {removed['surname']} {removed['name']}\n\n"
        "Qaysi o'quvchini tuzatmoqchisiz yoki o'chirmoqchisiz?",
        reply_markup=edit_list_kb(students),
    )
    await callback.answer("O'chirildi ✅")


@router.callback_query(ExamStates.edit_list, F.data.startswith("edit_score:"))
async def edit_score_start(callback: CallbackQuery, state: FSMContext):
    idx = int(callback.data.split(":")[1])
    data = await state.get_data()
    students = data.get("students", [])
    if idx >= len(students):
        await callback.answer("O'quvchi topilmadi.", show_alert=True)
        return
    s = students[idx]
    await state.update_data(editing_index=idx)

    if data["test_type"] == "unit":
        await state.set_state(ExamStates.edit_score_unit)
        await callback.message.edit_text(
            f"✏️ {s['surname']} {s['name']} — yangi ball nechi? (max {data['max_score']}):"
        )
    else:
        await state.set_state(ExamStates.edit_score_midterm)
        sec = data["sections"]
        await callback.message.edit_text(
            f"✏️ {s['surname']} {s['name']} — yangi ballarni <b>bitta xabarda</b>, "
            f"LISTENING READING WRITING SPEAKING tartibida kiriting.\n"
            f"(max: {sec['listening']} {sec['reading']} {sec['writing']} {sec['speaking']})\n\n"
            f"Masalan: 19 24 33 13"
        )
    await callback.answer()


@router.message(ExamStates.edit_score_unit)
async def edit_score_unit_save(message: Message, state: FSMContext):
    data = await state.get_data()
    val = await safe_float(message.text)
    if val is None or val < 0 or val > data["max_score"]:
        await message.answer(f"0 dan {data['max_score']}gacha son kiriting:")
        return

    idx = data["editing_index"]
    students = data.get("students", [])
    if idx >= len(students):
        await state.set_state(ExamStates.after_student)
        await message.answer("O'quvchi topilmadi.", reply_markup=after_student_kb())
        return

    percent = val / data["max_score"] * 100
    status = unit_status(percent)
    students[idx]["total"] = val
    students[idx]["percent"] = percent
    students[idx]["status"] = status
    await state.update_data(students=students)
    await state.set_state(ExamStates.after_student)
    await message.answer(
        f"✅ Yangilandi: {students[idx]['surname']} {students[idx]['name']} — "
        f"{percent:.1f}% — {status}\n\nDavom etamizmi?",
        reply_markup=after_student_kb(),
    )


@router.message(ExamStates.edit_score_midterm)
async def edit_score_midterm_save(message: Message, state: FSMContext):
    data = await state.get_data()
    sec = data["sections"]
    tokens = message.text.replace(",", ".").split()
    if len(tokens) != 4:
        await message.answer(
            "4 ta son kiriting (LISTENING READING WRITING SPEAKING), masalan: 19 24 33 13"
        )
        return
    try:
        l, r, w, sp = [float(t) for t in tokens]
    except ValueError:
        await message.answer("Faqat sonlar kiriting, masalan: 19 24 33 13")
        return
    if not (0 <= l <= sec["listening"] and 0 <= r <= sec["reading"]
            and 0 <= w <= sec["writing"] and 0 <= sp <= sec["speaking"]):
        await message.answer(
            f"Ballar max qiymatdan oshmasin (max: {sec['listening']} {sec['reading']} "
            f"{sec['writing']} {sec['speaking']}):"
        )
        return

    idx = data["editing_index"]
    students = data.get("students", [])
    if idx >= len(students):
        await state.set_state(ExamStates.after_student)
        await message.answer("O'quvchi topilmadi.", reply_markup=after_student_kb())
        return

    total = l + r + w + sp
    max_total = sum(sec.values())
    percent = total / max_total * 100
    status = midterm_status(percent)
    students[idx].update({
        "listening": l, "reading": r, "writing": w, "speaking": sp,
        "total": total, "percent": percent, "status": status,
    })
    await state.update_data(students=students)
    await state.set_state(ExamStates.after_student)
    await message.answer(
        f"✅ Yangilandi: {students[idx]['surname']} {students[idx]['name']} — "
        f"{percent:.1f}% — {status}\n\nDavom etamizmi?",
        reply_markup=after_student_kb(),
    )


@router.message(ExamStates.after_student, F.text == "✅ Tayyor")
async def finish_students(message: Message, state: FSMContext):
    data = await state.get_data()
    students = data.get("students", [])
    if not students:
        await message.answer("Hech bo'lmasa 1 ta o'quvchi kiriting.")
        return

    await state.update_data(retake_selected=[])
    await state.set_state(ExamStates.retake_marking)
    await message.answer(
        "Kimlarni natijalari <b>PASSED INDEX</b> va <b>GROUP INDEX</b>ga QO'SHILMASIN?\n\n"
        "☑️ Belgilangan (check qilingan) o'quvchilar — jadvalda ko'rinadi, "
        "lekin index'ga qo'shilmaydi.\n"
        "⬜️ Ochiq qoldirilganlar — index'ga qo'shiladi.",
        reply_markup=retake_checkbox_kb(students, []),
    )


# ---------- CHECKBOX ORQALI BELGILASH ----------

@router.callback_query(ExamStates.retake_marking, F.data.startswith("idx_toggle:"))
async def idx_toggle(callback: CallbackQuery, state: FSMContext):
    idx = int(callback.data.split(":")[1])
    data = await state.get_data()
    selected = set(data.get("retake_selected", []))
    if idx in selected:
        selected.remove(idx)
    else:
        selected.add(idx)
    selected = list(selected)
    await state.update_data(retake_selected=selected)
    await callback.message.edit_reply_markup(
        reply_markup=retake_checkbox_kb(data["students"], selected)
    )
    await callback.answer()


@router.callback_query(ExamStates.retake_marking, F.data == "idx_manual")
async def idx_manual_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(ExamStates.retake_manual_text)
    await callback.message.answer(
        "Index'ga QO'SHILMASIN deb hisoblagan o'quvchi(lar)ning FAMILIYA ISMini yozing.\n"
        "Bir nechta bo'lsa, har birini yangi qatorda yozing."
    )
    await callback.answer()


@router.message(ExamStates.retake_manual_text)
async def idx_manual_input(message: Message, state: FSMContext):
    data = await state.get_data()
    students = data["students"]
    selected = set(data.get("retake_selected", []))
    lines = [ln.strip() for ln in message.text.split("\n") if ln.strip()]

    not_found = []
    for line in lines:
        found = False
        for i, s in enumerate(students):
            full_name = f"{s['surname']} {s['name']}".lower()
            if line.lower() in full_name or full_name in line.lower():
                selected.add(i)
                found = True
                break
        if not found:
            not_found.append(line)

    await state.update_data(retake_selected=list(selected))
    await state.set_state(ExamStates.retake_marking)
    msg = "Belgilandi ✅ (index'ga qo'shilmaydi)"
    if not_found:
        msg += "\n\nTopilmadi: " + ", ".join(not_found)
    await message.answer(msg, reply_markup=retake_checkbox_kb(students, list(selected)))


@router.callback_query(ExamStates.retake_marking, F.data == "idx_confirm")
async def idx_confirm(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    students = data["students"]
    excluded = set(data.get("retake_selected", []))

    # Belgilangan (checked) o'quvchilar jadvalda qoladi, lekin index'ga qo'shilmaydi
    for i, s in enumerate(students):
        s["first_time"] = i in excluded
    await state.update_data(students=students)

    export_data = {
        "teacher": data["teacher"],
        "date": data["date"],
        "level": data["level"],
        "study_dates": data["study_dates"],
        "examiner": data["examiner"],
        "test_type": data["test_type"],
        "test_name": data["test_name"],
        "level_name": data["level_name"],
        "students": students,
    }
    if data["test_type"] == "unit":
        export_data["max_score"] = data["max_score"]
    else:
        export_data["sections"] = data["sections"]

    # 5) Guruh uchun o'quvchilar ro'yxatini keyingi safar uchun saqlash/yangilash
    branch = data.get("saved_branch")
    if not branch:
        user = await db.get_user(callback.from_user.id)
        branch = user["branch"] if user else None
    if branch and data.get("level_name"):
        seen = set()
        unique_students = []
        for s in students:
            key = (s["surname"].strip().lower(), s["name"].strip().lower())
            if key not in seen:
                seen.add(key)
                unique_students.append({"surname": s["surname"], "name": s["name"]})
        await db.save_group_students(branch, data["level_name"], unique_students)

    # 7) Statistika uchun natijalarni saqlash
    if students:
        percents = [s["percent"] for s in students]
        avg_percent = sum(percents) / len(percents)
        fail_count = sum(1 for s in students if s["status"] == "FAIL")
        pass_count = len(students) - fail_count
        examiner_user = await db.get_user(callback.from_user.id)
        await db.save_exam_result({
            "examiner_telegram_id": callback.from_user.id,
            "examiner_name": examiner_user["full_name"] if examiner_user else data.get("examiner"),
            "branch": branch,
            "test_type": data["test_type"],
            "test_name": data["test_name"],
            "group_name": data["level_name"],
            "students_count": len(students),
            "avg_percent": avg_percent,
            "pass_count": pass_count,
            "fail_count": fail_count,
        })

    os.makedirs("exports", exist_ok=True)
    filename = f"exports/exam_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    build_excel(export_data, filename)

    is_adm = await db.is_admin(callback.from_user.id)
    await callback.message.edit_text("✅ Excel fayl tayyorlanmoqda...")
    await callback.message.answer_document(FSInputFile(filename), caption="Imtihon natijalari tayyor 📊")

    # END OF COURSE / MIDTERM natijalari (test_type != "unit") — excel bir vaqtda
    # o'quv bo'lim rahbariga ham, filialdan qat'iy nazar, jo'natiladi
    if data["test_type"] != "unit":
        study_heads = await db.get_active_study_heads()
        if study_heads:
            caption = (
                f"📊 Imtihon natijalari — {data.get('test_name') or 'MIDTERM/END OF COURSE'}\n"
                f"Filial: {branch or '-'}\nExaminer: {data.get('examiner')}\n"
                f"Guruh: {data.get('level_name')}"
            )
            for sh in study_heads:
                try:
                    await callback.bot.send_document(
                        sh["telegram_id"], FSInputFile(filename), caption=caption
                    )
                except Exception:
                    pass

    # Fayl yuborib bo'lingach diskda saqlanib qolmasin — darhol o'chirib tashlaymiz
    try:
        os.remove(filename)
    except OSError:
        pass

    await callback.message.answer(
        "Yangi test kiritish uchun tugmani bosing:",
        reply_markup=build_main_menu_kb("EXAMINER", is_adm),
    )
    await state.clear()
    await callback.answer()
