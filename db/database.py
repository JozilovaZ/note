import json
from datetime import date, datetime

import aiosqlite
from cryptography.fernet import Fernet, InvalidToken

from config import DB_PATH, SECRET_KEY, TZ
from hemis.client import Lesson, Task

_fernet = Fernet(SECRET_KEY.encode())
_db: aiosqlite.Connection | None = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    telegram_id  INTEGER PRIMARY KEY,
    hemis_login  TEXT NOT NULL,
    token        TEXT,              -- shifrlangan; NULL bo'lsa qayta kirish kerak
    full_name    TEXT,
    group_name   TEXT,
    notify       INTEGER NOT NULL DEFAULT 1,
    remind_before INTEGER          -- NULL bo'lsa config.REMIND_BEFORE
);
CREATE TABLE IF NOT EXISTS lessons (
    telegram_id  INTEGER NOT NULL,
    day          TEXT NOT NULL,     -- YYYY-MM-DD
    start        TEXT NOT NULL,
    end          TEXT,
    pair         TEXT,
    subject      TEXT,
    room         TEXT,
    building     TEXT,
    kind         TEXT,
    teacher      TEXT
);
CREATE INDEX IF NOT EXISTS lessons_user_day ON lessons (telegram_id, day);
-- ma'lum bo'lgan NB'lar, yangisini aniqlash uchun
CREATE TABLE IF NOT EXISTS absences (
    telegram_id  INTEGER NOT NULL,
    key          TEXT NOT NULL,     -- sana|fan|para|tur
    excused      INTEGER NOT NULL,
    PRIMARY KEY (telegram_id, key)
);
-- topshiriqlar (fan resurslari), muddat eslatmalari uchun
CREATE TABLE IF NOT EXISTS tasks (
    telegram_id   INTEGER NOT NULL,
    id            INTEGER NOT NULL,
    subject_id    INTEGER,
    subject       TEXT,
    name          TEXT,
    deadline      INTEGER NOT NULL,  -- unix vaqt
    max_ball      INTEGER,
    attempt_limit INTEGER,
    attempt_count INTEGER,
    submitted     INTEGER NOT NULL,
    teacher       TEXT,
    files         TEXT,              -- JSON: [[nomi, url], ...]
    PRIMARY KEY (telegram_id, id)
);
-- yuborilgan eslatmalar, bir xabar ikki marta ketmasligi uchun
CREATE TABLE IF NOT EXISTS sent (
    telegram_id  INTEGER NOT NULL,
    key          TEXT NOT NULL,
    PRIMARY KEY (telegram_id, key)
);
"""


async def init() -> None:
    global _db
    _db = await aiosqlite.connect(DB_PATH)
    _db.row_factory = aiosqlite.Row
    await _db.executescript(SCHEMA)
    # eski bazaga yangi ustunni qo'shish
    async with _db.execute("PRAGMA table_info(users)") as cur:
        columns = {row["name"] for row in await cur.fetchall()}
    if "remind_before" not in columns:
        await _db.execute("ALTER TABLE users ADD COLUMN remind_before INTEGER")
    if "absences_synced" not in columns:
        # 0 bo'lsa davomat hali bir marta ham olinmagan: eski NB'lar uchun xabar yuborilmaydi
        await _db.execute("ALTER TABLE users ADD COLUMN absences_synced INTEGER NOT NULL DEFAULT 0")
    if "tasks_synced" not in columns:
        # 0 bo'lsa mavjud topshiriqlar "yangi" deb xabar qilinmaydi
        await _db.execute("ALTER TABLE users ADD COLUMN tasks_synced INTEGER NOT NULL DEFAULT 0")
    async with _db.execute("PRAGMA table_info(tasks)") as cur:
        task_columns = {row["name"] for row in await cur.fetchall()}
    if "files" not in task_columns:
        # tasks — HEMIS keshi, eski tuzilishdagisini qayta yaratamiz; keyingi sinxronlashda
        # mavjud topshiriqlar "yangi" deb xabar qilinmasligi uchun tasks_synced = 0
        await _db.execute("DROP TABLE tasks")
        await _db.executescript(SCHEMA)
        await _db.execute("UPDATE users SET tasks_synced = 0")
    await _db.commit()


async def close() -> None:
    if _db:
        await _db.close()


def decrypt_token(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return _fernet.decrypt(value.encode()).decode()
    except InvalidToken:
        return None


async def save_user(telegram_id: int, login: str, token: str, full_name: str, group: str) -> None:
    await _db.execute(
        """INSERT INTO users (telegram_id, hemis_login, token, full_name, group_name)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT (telegram_id) DO UPDATE SET
             absences_synced = CASE WHEN users.hemis_login = excluded.hemis_login
                                    THEN users.absences_synced ELSE 0 END,
             tasks_synced = CASE WHEN users.hemis_login = excluded.hemis_login
                                 THEN users.tasks_synced ELSE 0 END,
             hemis_login = excluded.hemis_login, token = excluded.token,
             full_name = excluded.full_name, group_name = excluded.group_name""",
        (telegram_id, login, _fernet.encrypt(token.encode()).decode(), full_name, group),
    )
    await _db.commit()


async def get_user(telegram_id: int) -> aiosqlite.Row | None:
    async with _db.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)) as cur:
        return await cur.fetchone()


async def logged_in_users() -> list[aiosqlite.Row]:
    async with _db.execute("SELECT * FROM users WHERE token IS NOT NULL") as cur:
        return list(await cur.fetchall())


async def invalidate_token(telegram_id: int) -> None:
    await _db.execute("UPDATE users SET token = NULL WHERE telegram_id = ?", (telegram_id,))
    await _db.commit()


async def set_notify(telegram_id: int, enabled: bool) -> None:
    await _db.execute("UPDATE users SET notify = ? WHERE telegram_id = ?", (int(enabled), telegram_id))
    await _db.commit()


async def set_remind_before(telegram_id: int, minutes: int) -> None:
    await _db.execute("UPDATE users SET remind_before = ? WHERE telegram_id = ?", (minutes, telegram_id))
    await _db.commit()


async def delete_user(telegram_id: int) -> None:
    for table in ("users", "lessons", "sent", "absences", "tasks"):
        await _db.execute(f"DELETE FROM {table} WHERE telegram_id = ?", (telegram_id,))
    await _db.commit()


async def replace_lessons(telegram_id: int, lessons: list[Lesson]) -> None:
    await _db.execute("DELETE FROM lessons WHERE telegram_id = ?", (telegram_id,))
    await _db.executemany(
        """INSERT INTO lessons (telegram_id, day, start, end, pair, subject, room, building, kind, teacher)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            (telegram_id, l.day.isoformat(), l.start, l.end, l.pair, l.subject,
             l.room, l.building, l.kind, l.teacher)
            for l in lessons
        ],
    )
    await _db.commit()


async def get_lessons(telegram_id: int, start: date, end: date | None = None) -> list[Lesson]:
    end = end or start
    async with _db.execute(
        "SELECT * FROM lessons WHERE telegram_id = ? AND day BETWEEN ? AND ? ORDER BY day, start",
        (telegram_id, start.isoformat(), end.isoformat()),
    ) as cur:
        rows = await cur.fetchall()
    return [
        Lesson(
            day=date.fromisoformat(r["day"]), start=r["start"], end=r["end"], pair=r["pair"],
            subject=r["subject"], room=r["room"], building=r["building"], kind=r["kind"],
            teacher=r["teacher"],
        )
        for r in rows
    ]


async def lesson_days(telegram_id: int) -> tuple[date, date] | None:
    """Bazadagi jadvalning birinchi va oxirgi kuni."""
    async with _db.execute(
        "SELECT MIN(day), MAX(day) FROM lessons WHERE telegram_id = ?", (telegram_id,)
    ) as cur:
        first, last = await cur.fetchone()
    return (date.fromisoformat(first), date.fromisoformat(last)) if first else None


async def known_absences(telegram_id: int) -> dict[str, bool]:
    async with _db.execute(
        "SELECT key, excused FROM absences WHERE telegram_id = ?", (telegram_id,)
    ) as cur:
        return {row["key"]: bool(row["excused"]) for row in await cur.fetchall()}


async def save_absences(telegram_id: int, absences: dict[str, bool]) -> None:
    """Davomat holatini to'liq almashtiradi va foydalanuvchini sinxronlangan deb belgilaydi."""
    await _db.execute("DELETE FROM absences WHERE telegram_id = ?", (telegram_id,))
    await _db.executemany(
        "INSERT INTO absences (telegram_id, key, excused) VALUES (?, ?, ?)",
        [(telegram_id, key, int(excused)) for key, excused in absences.items()],
    )
    await _db.execute("UPDATE users SET absences_synced = 1 WHERE telegram_id = ?", (telegram_id,))
    await _db.commit()


async def known_task_ids(telegram_id: int) -> set[int]:
    async with _db.execute("SELECT id FROM tasks WHERE telegram_id = ?", (telegram_id,)) as cur:
        return {row["id"] for row in await cur.fetchall()}


async def save_tasks(telegram_id: int, tasks: list[Task]) -> None:
    """Topshiriqlarni to'liq almashtiradi va foydalanuvchini sinxronlangan deb belgilaydi."""
    await _db.execute("DELETE FROM tasks WHERE telegram_id = ?", (telegram_id,))
    await _db.executemany(
        """INSERT INTO tasks (telegram_id, id, subject_id, subject, name, deadline, max_ball,
                              attempt_limit, attempt_count, submitted, teacher, files)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [(telegram_id, t.id, t.subject_id, t.subject, t.name, int(t.deadline.timestamp()), t.max_ball,
          t.attempt_limit, t.attempt_count, int(t.submitted), t.teacher, json.dumps(t.files))
         for t in tasks],
    )
    await _db.execute("UPDATE users SET tasks_synced = 1 WHERE telegram_id = ?", (telegram_id,))
    await _db.commit()


def _task(r: aiosqlite.Row) -> Task:
    return Task(
        id=r["id"], subject_id=r["subject_id"] or 0, subject=r["subject"], name=r["name"],
        deadline=datetime.fromtimestamp(r["deadline"], TZ), max_ball=r["max_ball"],
        attempt_limit=r["attempt_limit"], attempt_count=r["attempt_count"],
        submitted=bool(r["submitted"]), teacher=r["teacher"] or "",
        files=[tuple(f) for f in json.loads(r["files"] or "[]")],
    )


async def get_tasks(telegram_id: int) -> list[Task]:
    async with _db.execute(
        "SELECT * FROM tasks WHERE telegram_id = ? ORDER BY deadline", (telegram_id,)
    ) as cur:
        return [_task(r) for r in await cur.fetchall()]


async def pending_tasks(telegram_id: int, after: datetime) -> list[Task]:
    """Hali yuklanmagan va muddati o'tmagan topshiriqlar."""
    async with _db.execute(
        "SELECT * FROM tasks WHERE telegram_id = ? AND submitted = 0 AND deadline > ? ORDER BY deadline",
        (telegram_id, int(after.timestamp())),
    ) as cur:
        return [_task(r) for r in await cur.fetchall()]


async def mark_sent(telegram_id: int, key: str) -> bool:
    """Eslatma hali yuborilmagan bo'lsa belgilaydi va True qaytaradi."""
    cur = await _db.execute("INSERT OR IGNORE INTO sent (telegram_id, key) VALUES (?, ?)", (telegram_id, key))
    await _db.commit()
    return cur.rowcount == 1


async def cleanup_sent(today: date) -> None:
    """Kalitlar "YYYY-MM-DD|..." ko'rinishida, eski kunlarnikini o'chiradi."""
    await _db.execute("DELETE FROM sent WHERE key < ?", (today.isoformat(),))
    await _db.commit()
