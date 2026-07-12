from aiogram.fsm.state import State, StatesGroup


class ExamStates(StatesGroup):
    teacher = State()
    date = State()
    level = State()
    study_dates = State()
    examiner = State()
    test_type = State()

    # UNIT TEST
    unit_name = State()
    unit_level_name = State()
    unit_max_score = State()

    # MIDTERM / O'TISH TESTI
    midterm_name = State()
    midterm_level_name = State()
    sections_confirm = State()
    sections_edit_listening = State()
    sections_edit_reading = State()
    sections_edit_writing = State()
    sections_edit_speaking = State()

    # STUDENT ENTRY
    entry_mode_choice = State()
    bulk_entry = State()
    student_surname = State()
    student_name = State()
    student_score_unit = State()
    student_score_listening = State()
    student_score_reading = State()
    student_score_writing = State()
    student_score_speaking = State()
    after_student = State()

    # NATIJANI TUZATISH / O'CHIRISH
    edit_list = State()
    edit_score_unit = State()
    edit_score_midterm = State()

    # RETAKE MARKING
    retake_marking = State()
    retake_manual_text = State()

    # SAQLANGAN GURUHNI BOSHQARISH (o'quvchini o'chirish)
    manage_group_marking = State()


class RegStates(StatesGroup):
    choose_role = State()
    full_name = State()
    choose_branch = State()


class BookingStates(StatesGroup):
    choose_branch = State()
    exam_date = State()
    exam_time = State()
    test_type = State()
    unit_name = State()
    group_name = State()
    students_count = State()
    custom_field_input = State()
    confirm = State()

    # OXIRGI BUYURTMANI TAKRORLASH (avval imtihon topshirgan guruh)
    repeat_group_name = State()
    repeat_fields_select = State()
    repeat_branch = State()
    repeat_exam_date = State()
    repeat_exam_time = State()
    repeat_test_type = State()
    repeat_unit_name = State()
    repeat_students_count = State()

    # BUYURTMA VAQTINI KO'CHIRISH
    reschedule_pick = State()
    reschedule_date = State()
    reschedule_time = State()


class AdminStates(StatesGroup):
    search_query = State()
    reminder_input = State()
    branch_add_input = State()
    testtype_add_input = State()
    restore_db_upload = State()
    grading_input = State()
    booking_field_add_input = State()
    edit_name_input = State()
    broadcast_input = State()
    broadcast_confirm = State()
