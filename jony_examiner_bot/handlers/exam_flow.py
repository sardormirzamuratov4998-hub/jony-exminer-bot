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
    retake_kb,
    cancel_kb,
    start_kb,
)
from excel_export import build_excel

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


# ---------- BOSHLASH ----------

@router.message(F.text == "🆕 Test kiritish")
async def start_exam(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(ExamStates.teacher)
    await message.answer(
        "📋 Yangi test kiritish boshlandi.\n\nO'qituvchi ismini kiriting (TEACHER):",
        reply_markup=cancel_kb(),
    )


@router.message(F.text == "❌ Bekor qilish")
async def cancel_flow(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Bekor qilindi.", reply_markup=start_kb())


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
    await state.set_state(ExamStates.student_surname)
    await message.answer("Endi o'quvchilarni kiritamiz.\n\n1-o'quvchining FAMILIYASI:")


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
    await state.set_state(ExamStates.student_surname)
    await callback.message.edit_text("Standart ballar qabul qilindi ✅")
    await callback.message.answer("Endi o'quvchilarni kiritamiz.\n\n1-o'quvchining FAMILIYASI:")
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
    await state.set_state(ExamStates.student_surname)
    await message.answer("Ballar saqlandi ✅\n\nEndi o'quvchilarni kiritamiz.\n\n1-o'quvchining FAMILIYASI:")


# ---------- O'QUVCHI KIRITISH ----------

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
    await state.set_state(ExamStates.student_surname)
    await message.answer("Keyingi o'quvchining FAMILIYASI:")


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
        "Qaysi o'quvchi(lar) BIRINCHI MARTA emas, QAYTA topshirmoqda?\n"
        "(Ularni belgilang — ular GROUP/PASSING INDEKSGA qo'shiladi, "
        "birinchi marta topshirganlar esa jadvalda ko'rinadi lekin indeksga kirmaydi)",
        reply_markup=retake_kb(students, []),
    )


# ---------- RETAKE BELGILASH ----------

@router.callback_query(ExamStates.retake_marking, F.data.startswith("retake_toggle:"))
async def toggle_retake(callback: CallbackQuery, state: FSMContext):
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
        reply_markup=retake_kb(data["students"], selected)
    )
    await callback.answer()


@router.callback_query(ExamStates.retake_marking, F.data == "retake_manual")
async def retake_manual_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(ExamStates.retake_manual_text)
    await callback.message.answer(
        "Qayta topshirgan o'quvchi(lar)ning FAMILIYA ISM'ini yozing.\n"
        "Bir nechta bo'lsa, har birini yangi qatorda yozing."
    )
    await callback.answer()


@router.message(ExamStates.retake_manual_text)
async def retake_manual_input(message: Message, state: FSMContext):
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
    msg = "Belgilandi ✅"
    if not_found:
        msg += "\n\nTopilmadi: " + ", ".join(not_found)
    await message.answer(msg, reply_markup=retake_kb(students, list(selected)))


@router.callback_query(ExamStates.retake_marking, F.data == "retake_confirm")
async def retake_confirm(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    students = data["students"]
    selected = set(data.get("retake_selected", []))

    for i, s in enumerate(students):
        s["first_time"] = i not in selected

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

    os.makedirs("exports", exist_ok=True)
    filename = f"exports/exam_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    build_excel(export_data, filename)

    await callback.message.edit_text("✅ Excel fayl tayyorlanmoqda...")
    await callback.message.answer_document(FSInputFile(filename), caption="Imtihon natijalari tayyor 📊")
    await callback.message.answer("Yangi test kiritish uchun tugmani bosing:", reply_markup=start_kb())
    await state.clear()
    await callback.answer()
