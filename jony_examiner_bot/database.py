import aiosqlite
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
