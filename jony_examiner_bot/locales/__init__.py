"""
i18n (ko'p tillilik) uchun asosiy modul.

Foydalanish:
    from locales import t
    text = t("choose_language", lang)

Yangi til qo'shish uchun (masalan ingliz tili):
    1. locales/en.py faylini yarating va ichiga:
           TRANSLATIONS = {
               "language_name": "English",
               ...  # uz.py dagi HAR BIR kalitni shu yerga ham tarjima qiling
           }
       deb yozing (uz.py dagi kalitlar ro'yxatini asos qiling).
    2. Quyida `from locales import en` qatorini qo'shing.
    3. LANGUAGES lug'atiga `"en": "🇬🇧 English"` qatorini qo'shing.
    4. _MODULES lug'atiga `"en": en.TRANSLATIONS` qatorini qo'shing.
    5. database.py dagi SUPPORTED_LANGUAGES ro'yxatiga "en" ni qo'shing.

Batafsil qadamlar 7-bosqichda README.md faylida yoziladi.
"""

from locales import uz, ru

DEFAULT_LANGUAGE = "uz"

# Tanlov tugmalarida ko'rsatiladigan til nomlari (kod: ko'rinadigan nom)
LANGUAGES = {
    "uz": "🇺🇿 O'zbekcha",
    "ru": "🇷🇺 Русский",
}

_MODULES = {
    "uz": uz.TRANSLATIONS,
    "ru": ru.TRANSLATIONS,
}


def t(key: str, lang: str = DEFAULT_LANGUAGE, **kwargs) -> str:
    """Berilgan kalit uchun, berilgan tildagi matnni qaytaradi.

    - Agar `lang` noma'lum bo'lsa — standart til (uz) ishlatiladi.
    - Agar shu tilda kalit tarjima qilinmagan bo'lsa — standart tildan olinadi.
    - Agar standart tilda ham topilmasa — kalitning o'zi qaytariladi
      (bot hech qachon xato bilan to'xtab qolmasligi uchun).
    - kwargs berilsa, matn ichidagi {placeholder} larga joylashtiriladi
      (masalan: t("greeting", lang, name="Aziz") -> "Salom, Aziz!").
    """
    lang = lang if lang in _MODULES else DEFAULT_LANGUAGE
    text = _MODULES.get(lang, {}).get(key)
    if text is None:
        text = _MODULES.get(DEFAULT_LANGUAGE, {}).get(key, key)
    if kwargs:
        try:
            text = text.format(**kwargs)
        except (KeyError, IndexError):
            pass
    return text
