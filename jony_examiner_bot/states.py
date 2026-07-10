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

    # RETAKE MARKING
    retake_marking = State()
    retake_manual_text = State()


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
    midterm_choice = State()
    group_name = State()
    students_count = State()
    confirm = State()


class AdminStates(StatesGroup):
    pass

