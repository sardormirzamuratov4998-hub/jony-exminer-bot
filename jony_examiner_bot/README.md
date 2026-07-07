# Jony Academy Examiner Bot

Examiner test natijalarini kiritish va Excel formatda chiqarish uchun Telegram bot.

## Xususiyatlari

- **Test turi tanlash**: UNIT TEST (bitta % ball) yoki MIDTERM/O'TISH TESTI (Listening/Reading/Writing/Speaking bo'yicha)
- **Header ma'lumotlari**: Teacher, Date, Level, Study dates, Examiner
- **O'quvchi qo'shish**: cheksiz sonda, ketma-ket
- **Avtomatik status**:
  - UNIT TEST: FAIL (<64%) / BAD (64-72%) / AVERAGE (73-83%) / GOOD (84-94%) / EXCELLENT (95-100%)
  - MIDTERM: PASS (>=60%) / FAIL (<60%)
- **Qayta topshirganlarni belgilash**: checkbox yoki qo'lda ism kiritish orqali
- **GROUP INDEX / PASSING INDEX**: faqat QAYTA topshirganlar asosida hisoblanadi (birinchi marta topshirganlar jadvalda ko'rinadi, lekin indeksga qo'shilmaydi)
- **Excel eksport**: rasmdagi shablon bo'yicha rangli, formatlangan jadval

## Railway'ga deploy qilish

1. Bu papkani GitHub repo qilib yuklang (yoki Railway CLI orqali to'g'ridan-to'g'ri deploy qiling)
2. Railway'da **New Project → Deploy from GitHub repo** tanlang
3. **Variables** bo'limiga o'ting va qo'shing:
   ```
   BOT_TOKEN=<BotFather'dan olingan token>
   ```
4. Railway avtomatik `requirements.txt` ni o'qib kutubxonalarni o'rnatadi va `Procfile` orqali botni ishga tushiradi (`worker: python bot.py`)
5. Deploy tugagach, botga `/start` yuboring

## Lokal ishga tushirish (test uchun)

```bash
pip install -r requirements.txt
cp .env.example .env
# .env faylga BOT_TOKEN ni yozing
python bot.py
```

## Fayllar tuzilishi

```
jony_examiner_bot/
├── bot.py                  # botni ishga tushiruvchi asosiy fayl
├── states.py                # FSM holatlari
├── keyboards.py              # tugmalar (inline/reply)
├── excel_export.py            # Excel fayl generatsiyasi (openpyxl)
├── handlers/
│   ├── start.py              # /start komandasi
│   └── exam_flow.py           # butun test kiritish jarayoni
├── requirements.txt
├── Procfile                  # Railway uchun start komandasi
├── railway.json               # Railway konfiguratsiyasi
└── .env.example
```

## Muhim eslatma

- SQLite yoki boshqa DB ishlatilmagan — har bir test kiritish sessiyasi vaqtinchalik
  (RAM'dagi FSM state) saqlanadi va "Tayyor" bosilgach Excel fayl sifatida yuboriladi.
- Agar keyinchalik barcha natijalarni tarixiy saqlash (masalan SQLite bazasiga yozish)
  kerak bo'lsa, buni alohida so'rab qo'shish mumkin.
