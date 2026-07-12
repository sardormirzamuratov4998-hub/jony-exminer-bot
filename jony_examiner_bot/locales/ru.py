"""Rus tili tarjimalari.

uz.py dagi har bir kalit shu yerda ham bo'lishi kerak — kalitlar
ro'yxati uz.py bilan bir xil tartibda saqlanadi, shunda solishtirish
va yangi tarjima qo'shish osonroq bo'ladi.
"""

TRANSLATIONS = {
    "language_name": "Русский",
    "choose_language": "Выберите язык:",
    "language_changed": "✅ Язык изменён на русский.",
    "change_language_button": "🌐 Изменить язык",

    # ---- 3-этап: registration.py / start.py ----
    "reg_removed_account": "Ваш аккаунт удалён администратором. Обратитесь к администратору.",
    "reg_teacher_welcome": (
        "Добро пожаловать, {name}! (филиал {branch})\n\n"
        "Нажмите кнопку, чтобы заказать экзамен.\n"
        "(Изменить роль: /change_role)"
    ),
    "reg_examiner_rejected": "К сожалению, ваш запрос отклонён. Обратитесь к администратору.",
    "reg_examiner_welcome": (
        "Добро пожаловать, {name}! (филиал {branch}, экзаменатор)\n\n"
        "Нажмите кнопку, чтобы вводить результаты тестов. Здесь же вы будете "
        "получать уведомления о новых заявках на экзамен по вашему филиалу.\n"
        "(Изменить роль: /change_role)"
    ),
    "role_choice_prompt": (
        "Здравствуйте! 👋\nДобро пожаловать в <b>Jony Academy Bot</b>.\n\n"
        "Сначала зарегистрируемся. Кто вы?"
    ),
    "role_btn_teacher": "👩‍🏫 Я учитель",
    "role_btn_examiner": "🧑‍💼 Я экзаменатор",
    "change_role_prompt": "Выберите вашу роль:",
    "reg_ask_full_name": "Введите имя и фамилию:",
    "reg_ask_branch": "Выберите ваш филиал:",
    "reg_done": "Вы зарегистрированы ✅\nФилиал: {branch}",
    "reg_teacher_book_hint": "Нажмите кнопку, чтобы заказать экзамен:",
    "reg_examiner_enter_hint": "Нажмите кнопку, чтобы вводить результаты тестов:",
    "menu_add_branch": "➕ Добавить филиал",
    "add_branch_already_all": "Вы уже добавлены во все филиалы.",
    "add_branch_choose": "Какой филиал хотите добавить?",
    "add_branch_added": "✅ Филиал {branch} добавлен.",
    "examiner_approved_msg": "Поздравляем! Ваш запрос одобрен ✅\n\nТеперь нажмите /start.",
    "examiner_rejected_msg": "К сожалению, ваш запрос отклонён. Обратитесь к администратору.",
    "whoami_not_registered": "Вы ещё не зарегистрированы. Нажмите /start.",
    "whoami_info": "Имя: {name}\nРоль: {role}\nФилиал: {branch}{branches}\nСтатус: {status}",
    "whoami_branches": "\nФилиалы: {list}",
}
