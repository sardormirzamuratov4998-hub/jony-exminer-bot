import aiosqlite
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

DB_PATH = "jony_bookings.db"

BRANCHES = ["Zafar", "Bekobod", "Stretinka"]

TASHKENT_TZ = ZoneInfo("Asia/Tashkent")


def now_tashkent() -> datetime:
    """Server qayerda joylashgan bo'lishidan qat'iy nazar, doim Toshkent
    mahalliy vaqtini (naive datetime sifatida) qaytaradi. Buyurtmalardagi
    sana/vaqt ham foydalanuvchi tomonidan Toshkent vaqtida kiritiladi,
    shuning uchun taqqoslashlar shu funksiya orqali izchil bo'lishi kerak."""
    return datetime.now(TASHKENT_TZ).replace(tzinfo=None)


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER UNIQUE NOT NULL,
                role TEXT NOT NULL,          -- TEACHER | EXAMINER
                full_name TEXT NOT NULL,
                branch TEXT NOT NULL,        -- asosiy (birinchi) filial
                status TEXT NOT NULL,        -- active | pending | approved | rejected | removed
                username TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS teacher_branches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER NOT NULL,
                branch TEXT NOT NULL,
                UNIQUE(telegram_id, branch)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS bookings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                teacher_telegram_id INTEGER NOT NULL,
                teacher_name TEXT NOT NULL,
                branch TEXT NOT NULL,
                exam_date TEXT NOT NULL,      -- DD.MM.YYYY
                exam_time TEXT NOT NULL,      -- HH:MM
                test_type TEXT NOT NULL,      -- UNIT TEST | END OF COURSE / MIDTERM
                test_name TEXT,               -- e.g. "Unit 7"
                group_name TEXT NOT NULL,     -- e.g. "Step 3 (Vikings)"
                students_count INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',  -- pending | accepted | cancelled | expired
                examiner_telegram_id INTEGER,
                examiner_name TEXT,
                created_at TEXT NOT NULL,
                accepted_at TEXT,
                reminder_1h_sent INTEGER DEFAULT 0,
                reminder_time_sent INTEGER DEFAULT 0,
                escalated INTEGER DEFAULT 0
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS booking_notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                booking_id INTEGER NOT NULL,
                chat_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                telegram_id INTEGER PRIMARY KEY,
                full_name TEXT,
                username TEXT,
                added_by INTEGER,
                added_at TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS saved_group_students (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                branch TEXT NOT NULL,
                group_name TEXT NOT NULL,
                students_json TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(branch, group_name)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS exam_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                examiner_telegram_id INTEGER,
                examiner_name TEXT,
                branch TEXT,
                test_type TEXT,           -- unit | midterm
                test_name TEXT,
                group_name TEXT,
                students_count INTEGER NOT NULL,
                avg_percent REAL NOT NULL,
                pass_count INTEGER NOT NULL,
                fail_count INTEGER NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        await db.commit()


# ---------- ADMINS ----------

async def is_admin(telegram_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db_:
        cur = await db_.execute("SELECT 1 FROM admins WHERE telegram_id=?", (telegram_id,))
        return await cur.fetchone() is not None


async def add_admin(telegram_id: int, full_name: str = None, username: str = None, added_by: int = None):
    async with aiosqlite.connect(DB_PATH) as db_:
        await db_.execute(
            "INSERT OR IGNORE INTO admins (telegram_id, full_name, username, added_by, added_at) "
            "VALUES (?,?,?,?,?)",
            (telegram_id, full_name, username, added_by, now_tashkent().isoformat()),
        )
        await db_.commit()


async def remove_admin(telegram_id: int):
    async with aiosqlite.connect(DB_PATH) as db_:
        await db_.execute("DELETE FROM admins WHERE telegram_id=?", (telegram_id,))
        await db_.commit()


async def list_admins():
    async with aiosqlite.connect(DB_PATH) as db_:
        db_.row_factory = aiosqlite.Row
        cur = await db_.execute("SELECT * FROM admins")
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


# ---------- SETTINGS ----------

async def set_setting(key: str, value: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
        await db.commit()


async def get_setting(key: str):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT value FROM settings WHERE key=?", (key,))
        row = await cur.fetchone()
        return row[0] if row else None


# ---------- USERS ----------

async def get_user(telegram_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM users WHERE telegram_id=?", (telegram_id,))
        row = await cur.fetchone()
        return dict(row) if row else None


async def upsert_user(telegram_id: int, role: str, full_name: str, branch: str, status: str, username: str = None):
    """Foydalanuvchi mavjud bo'lsa yangilaydi (rol o'zgartirish uchun), bo'lmasa yaratadi."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO users (telegram_id, role, full_name, branch, status, username)
               VALUES (?,?,?,?,?,?)
               ON CONFLICT(telegram_id) DO UPDATE SET
                 role=excluded.role, full_name=excluded.full_name,
                 branch=excluded.branch, status=excluded.status, username=excluded.username""",
            (telegram_id, role, full_name, branch, status, username),
        )
        await db.commit()


async def update_user_status(telegram_id: int, status: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET status=? WHERE telegram_id=?", (status, telegram_id))
        await db.commit()


async def get_pending_examiners():
    async with aiosqlite.connect(DB_PATH) as db_:
        db_.row_factory = aiosqlite.Row
        cur = await db_.execute("SELECT * FROM users WHERE role='EXAMINER' AND status='pending'")
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


async def get_all_staff():
    """Barcha ustoz va examinerlar (o'chirilganlardan tashqari)."""
    async with aiosqlite.connect(DB_PATH) as db_:
        db_.row_factory = aiosqlite.Row
        cur = await db_.execute(
            "SELECT * FROM users WHERE status != 'removed' ORDER BY branch, role, full_name"
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


async def get_user_by_row_id(user_row_id: int):
    async with aiosqlite.connect(DB_PATH) as db_:
        db_.row_factory = aiosqlite.Row
        cur = await db_.execute("SELECT * FROM users WHERE id=?", (user_row_id,))
        row = await cur.fetchone()
        return dict(row) if row else None


async def deactivate_user_by_row_id(user_row_id: int):
    async with aiosqlite.connect(DB_PATH) as db_:
        await db_.execute("UPDATE users SET status='removed' WHERE id=?", (user_row_id,))
        await db_.commit()


async def reactivate_user_by_row_id(user_row_id: int):
    user = await get_user_by_row_id(user_row_id)
    if not user:
        return
    async with aiosqlite.connect(DB_PATH) as db_:
        await db_.execute("UPDATE users SET status='active' WHERE id=?", (user_row_id,))
        await db_.commit()


async def get_active_bookings():
    """Faol buyurtmalar — muddati o'tmagan pending/accepted."""
    today = now_tashkent().strftime("%d.%m.%Y")
    async with aiosqlite.connect(DB_PATH) as db_:
        db_.row_factory = aiosqlite.Row
        cur = await db_.execute(
            "SELECT * FROM bookings WHERE status IN ('pending','accepted') ORDER BY exam_date, exam_time"
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


async def get_teacher_bookings(telegram_id: int, limit: int = 20):
    """Ustozning barcha buyurtmalari (pending/accepted/cancelled/expired) — eng oxirgisi birinchi."""
    async with aiosqlite.connect(DB_PATH) as db_:
        db_.row_factory = aiosqlite.Row
        cur = await db_.execute(
            "SELECT * FROM bookings WHERE teacher_telegram_id=? ORDER BY created_at DESC LIMIT ?",
            (telegram_id, limit),
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


async def get_examiners_by_branch(branch: str, status: str = "active"):
    """'active' va eski 'approved' statusli examinerlarni ham qamrab oladi (eski ma'lumotlar bilan mos)."""
    statuses = ["active", "approved"] if status == "active" else [status]
    placeholders = ",".join("?" * len(statuses))
    async with aiosqlite.connect(DB_PATH) as db_:
        db_.row_factory = aiosqlite.Row
        cur = await db_.execute(
            f"SELECT * FROM users WHERE role='EXAMINER' AND branch=? AND status IN ({placeholders})",
            (branch, *statuses),
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


# ---------- TEACHER BRANCHES (bir nechta filialda ishlash) ----------

async def add_teacher_branch(telegram_id: int, branch: str):
    async with aiosqlite.connect(DB_PATH) as db_:
        await db_.execute(
            "INSERT OR IGNORE INTO teacher_branches (telegram_id, branch) VALUES (?,?)",
            (telegram_id, branch),
        )
        await db_.commit()


async def get_teacher_branches(telegram_id: int):
    async with aiosqlite.connect(DB_PATH) as db_:
        cur = await db_.execute(
            "SELECT branch FROM teacher_branches WHERE telegram_id=? ORDER BY branch", (telegram_id,)
        )
        rows = await cur.fetchall()
        return [r[0] for r in rows]


# ---------- BOOKINGS ----------

async def create_booking(data: dict) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """INSERT INTO bookings
               (teacher_telegram_id, teacher_name, branch, exam_date, exam_time,
                test_type, test_name, group_name, students_count, status, created_at)
               VALUES (?,?,?,?,?,?,?,?,?, 'pending', ?)""",
            (
                data["teacher_telegram_id"], data["teacher_name"], data["branch"],
                data["exam_date"], data["exam_time"], data["test_type"],
                data.get("test_name"), data["group_name"], data["students_count"],
                now_tashkent().isoformat(),
            ),
        )
        await db.commit()
        return cur.lastrowid


async def get_booking(booking_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM bookings WHERE id=?", (booking_id,))
        row = await cur.fetchone()
        return dict(row) if row else None


async def accept_booking(booking_id: int, examiner_telegram_id: int, examiner_name: str) -> bool:
    """Returns True if successfully accepted (was pending), False if already taken."""
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT status FROM bookings WHERE id=?", (booking_id,))
        row = await cur.fetchone()
        if not row or row[0] != "pending":
            return False
        await db.execute(
            "UPDATE bookings SET status='accepted', examiner_telegram_id=?, examiner_name=?, accepted_at=? WHERE id=?",
            (examiner_telegram_id, examiner_name, now_tashkent().isoformat(), booking_id),
        )
        await db.commit()
        return True


async def examiner_has_conflict(examiner_telegram_id: int, exam_date: str, exam_time: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """SELECT COUNT(*) FROM bookings
               WHERE examiner_telegram_id=? AND exam_date=? AND exam_time=? AND status='accepted'""",
            (examiner_telegram_id, exam_date, exam_time),
        )
        row = await cur.fetchone()
        return row[0] > 0


async def add_notification(booking_id: int, chat_id: int, message_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO booking_notifications (booking_id, chat_id, message_id) VALUES (?,?,?)",
            (booking_id, chat_id, message_id),
        )
        await db.commit()


async def get_notifications(booking_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM booking_notifications WHERE booking_id=?", (booking_id,))
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


async def get_pending_bookings_older_than(hours: int):
    cutoff = now_tashkent().timestamp() - hours * 3600
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM bookings WHERE status='pending' AND escalated=0")
        rows = await cur.fetchall()
        result = []
        for r in rows:
            d = dict(r)
            created = datetime.fromisoformat(d["created_at"]).timestamp()
            if created <= cutoff:
                result.append(d)
        return result


async def get_all_pending_bookings():
    """Hali hech kim qabul qilmagan (pending) barcha buyurtmalar.
    Har kuni soat 18:00dagi filial examinerlariga ogohlantirish uchun ishlatiladi."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM bookings WHERE status='pending' ORDER BY exam_date, exam_time")
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


async def mark_escalated(booking_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE bookings SET escalated=1 WHERE id=?", (booking_id,))
        await db.commit()


async def get_accepted_bookings_needing_reminder():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM bookings WHERE status='accepted' AND (reminder_1h_sent=0 OR reminder_time_sent=0)"
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


async def mark_reminder_sent(booking_id: int, which: str):
    col = "reminder_1h_sent" if which == "1h" else "reminder_time_sent"
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f"UPDATE bookings SET {col}=1 WHERE id=?", (booking_id,))
        await db.commit()


async def cancel_booking(booking_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE bookings SET status='cancelled' WHERE id=?", (booking_id,))
        await db.commit()


async def expire_past_bookings():
    """Imtihon sanasi+vaqti o'tib ketgan, hali pending/accepted holatidagi
    buyurtmalarni 'expired' deb belgilaydi."""
    now = now_tashkent()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM bookings WHERE status IN ('pending','accepted')")
        rows = await cur.fetchall()
        expired_ids = []
        for r in rows:
            d = dict(r)
            try:
                exam_dt = datetime.strptime(f"{d['exam_date']} {d['exam_time']}", "%d.%m.%Y %H:%M")
            except ValueError:
                continue
            if exam_dt < now:
                expired_ids.append(d["id"])
        for bid in expired_ids:
            await db.execute("UPDATE bookings SET status='expired' WHERE id=?", (bid,))
        await db.commit()
        return expired_ids


async def get_daily_report(date_str: str):
    """date_str format: DD.MM.YYYY. Kunlik hisobot uchun ma'lumot."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        # Shu kuni yaratilgan buyurtmalar, filial bo'yicha
        cur = await db.execute("SELECT * FROM bookings")
        rows = await cur.fetchall()

        created_today_by_branch = {}
        accepted_today_by_examiner = {}

        for r in rows:
            d = dict(r)
            created_date = datetime.fromisoformat(d["created_at"]).strftime("%d.%m.%Y")
            if created_date == date_str:
                created_today_by_branch[d["branch"]] = created_today_by_branch.get(d["branch"], 0) + 1

            if d["accepted_at"]:
                accepted_date = datetime.fromisoformat(d["accepted_at"]).strftime("%d.%m.%Y")
                if accepted_date == date_str:
                    name = d["examiner_name"] or "Noma'lum"
                    accepted_today_by_examiner[name] = accepted_today_by_examiner.get(name, 0) + 1

        return {
            "created_today_by_branch": created_today_by_branch,
            "accepted_today_by_examiner": accepted_today_by_examiner,
        }


# ---------- 4) EXAMINERNING SHAXSIY JADVALI ----------

async def get_examiner_upcoming_bookings(examiner_telegram_id: int):
    """Shu examiner qabul qilgan, hali muddati o'tmagan (status='accepted') buyurtmalar."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM bookings WHERE examiner_telegram_id=? AND status='accepted' "
            "ORDER BY exam_date, exam_time",
            (examiner_telegram_id,),
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


# ---------- 5) SAQLANGAN O'QUVCHILAR RO'YXATI (guruh bo'yicha) ----------
# Guruh nomi katta-kichik harf/bo'sh joyларга qaramay bir xil deb hisoblanadi.
# Eski (oldin turli xil harf bilan saqlangan) yozuvlar bilan ham mos ishlashi
# uchun saqlashda ustunni o'zgartirmasdan, har doim mavjud yozuvni CASE-INSENSITIVE
# qidirib topamiz va aynan o'sha qatorni yangilaymiz.

def _norm_group(group_name: str) -> str:
    return (group_name or "").strip().lower()


async def _find_group_row(db, branch: str, group_name: str):
    """Berilgan filial + guruh nomiga case-insensitive mos keladigan qatorni topadi."""
    key = _norm_group(group_name)
    cur = await db.execute(
        "SELECT id, group_name, students_json FROM saved_group_students WHERE branch=?",
        (branch,),
    )
    rows = await cur.fetchall()
    for row in rows:
        if _norm_group(row[1]) == key:
            return row  # (id, group_name, students_json)
    return None


async def get_saved_group_students(branch: str, group_name: str):
    """Shu filial + guruh nomi uchun oldin saqlangan o'quvchilar (surname/name), yoki bo'sh ro'yxat.
    Guruh nomi katta-kichik harfga qaramay solishtiriladi."""
    if not branch or not group_name:
        return []
    async with aiosqlite.connect(DB_PATH) as db:
        row = await _find_group_row(db, branch, group_name)
        if not row:
            return []
        try:
            return json.loads(row[2])
        except (json.JSONDecodeError, TypeError):
            return []


async def _set_group_students(branch: str, group_name: str, students: list):
    """Ro'yxatni TO'LIQ ALMASHTIRIB saqlaydi (ichki funksiya — merge qilmaydi).
    Mavjud (case-insensitive mos) qator bo'lsa shuni yangilaydi, bo'lmasa yangi qo'shadi."""
    if not branch or not group_name:
        return
    students_json = json.dumps(students, ensure_ascii=False)
    async with aiosqlite.connect(DB_PATH) as db:
        existing = await _find_group_row(db, branch, group_name)
        if existing:
            await db.execute(
                "UPDATE saved_group_students SET students_json=?, updated_at=? WHERE id=?",
                (students_json, now_tashkent().isoformat(), existing[0]),
            )
        else:
            await db.execute(
                """INSERT INTO saved_group_students (branch, group_name, students_json, updated_at)
                   VALUES (?,?,?,?)""",
                (branch, group_name, students_json, now_tashkent().isoformat()),
            )
        await db.commit()


async def save_group_students(branch: str, group_name: str, students: list):
    """Shu filial + guruh uchun o'quvchilar ro'yxatini BIRLASHTIRIB (merge) saqlaydi:
    yangi kiritilgan o'quvchilar eski ro'yxatga QO'SHILADI (takrorlanmasdan),
    lekin eski o'quvchilar o'chib ketmaydi. Faqat "guruhdan o'chirish" funksiyasi
    orqaligina o'quvchi butunlay olib tashlanadi."""
    if not branch or not group_name:
        return
    existing = await get_saved_group_students(branch, group_name)
    seen = {(s["surname"].strip().lower(), s["name"].strip().lower()) for s in existing}
    merged = list(existing)
    for s in students:
        key = (s["surname"].strip().lower(), s["name"].strip().lower())
        if key not in seen:
            seen.add(key)
            merged.append({"surname": s["surname"], "name": s["name"]})
    await _set_group_students(branch, group_name, merged)


async def remove_students_from_group(branch: str, group_name: str, indices_to_remove: list):
    """Saqlangan guruh ro'yxatidan berilgan index'dagi o'quvchi(lar)ni o'chiradi
    va yangilangan ro'yxatni qaytaradi."""
    current = await get_saved_group_students(branch, group_name)
    remaining = [s for i, s in enumerate(current) if i not in set(indices_to_remove)]
    await _set_group_students(branch, group_name, remaining)
    return remaining


# ---------- 6) ADMIN QIDIRUV/FILTR ----------

async def search_bookings(query: str, limit: int = 20):
    """Ustoz ismi, guruh nomi, filial yoki test turi bo'yicha qidiradi."""
    like = f"%{query.strip()}%"
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """SELECT * FROM bookings
               WHERE teacher_name LIKE ? OR group_name LIKE ? OR branch LIKE ? OR test_type LIKE ?
               ORDER BY exam_date DESC, exam_time DESC
               LIMIT ?""",
            (like, like, like, like, limit),
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


# ---------- 7) STATISTIK DASHBOARD ----------

async def save_exam_result(data: dict):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO exam_results
               (examiner_telegram_id, examiner_name, branch, test_type, test_name,
                group_name, students_count, avg_percent, pass_count, fail_count, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                data.get("examiner_telegram_id"), data.get("examiner_name"), data.get("branch"),
                data.get("test_type"), data.get("test_name"), data.get("group_name"),
                data["students_count"], data["avg_percent"], data["pass_count"], data["fail_count"],
                now_tashkent().isoformat(),
            ),
        )
        await db.commit()


async def get_stats(days: int = 30):
    """Oxirgi N kunlik statistika: buyurtmalar, filial/examiner kesimida, o'rtacha ballar."""
    cutoff_iso = (now_tashkent() - timedelta(days=days)).isoformat()

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM bookings WHERE created_at >= ?", (cutoff_iso,))
        bookings = [dict(r) for r in await cur.fetchall()]

        cur = await db.execute("SELECT * FROM exam_results WHERE created_at >= ?", (cutoff_iso,))
        results = [dict(r) for r in await cur.fetchall()]

    total_bookings = len(bookings)
    accepted_bookings = sum(1 for b in bookings if b["accepted_at"])

    by_branch = {}
    for b in bookings:
        by_branch[b["branch"]] = by_branch.get(b["branch"], 0) + 1

    by_examiner = {}
    for r in results:
        name = r["examiner_name"] or "Noma'lum"
        entry = by_examiner.setdefault(name, {"count": 0, "_total_percent": 0.0})
        entry["count"] += 1
        entry["_total_percent"] += r["avg_percent"]
    for entry in by_examiner.values():
        entry["avg_percent"] = entry["_total_percent"] / entry["count"] if entry["count"] else 0
        del entry["_total_percent"]

    total_pass = sum(r["pass_count"] for r in results)
    total_fail = sum(r["fail_count"] for r in results)

    overall_avg_percent = None
    if results:
        total_n = sum(r["students_count"] for r in results)
        if total_n:
            overall_avg_percent = sum(r["avg_percent"] * r["students_count"] for r in results) / total_n

    return {
        "total_bookings": total_bookings,
        "accepted_bookings": accepted_bookings,
        "by_branch": by_branch,
        "by_examiner": by_examiner,
        "overall_avg_percent": overall_avg_percent,
        "total_pass": total_pass,
        "total_fail": total_fail,
    }
