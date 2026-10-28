"""HEMIS talaba API'si bilan ishlash.

Endpoint'lar HEMIS mobil ilovasi ishlatadigan /rest/v1 API'siga asoslangan.
Javob formati: {"success": bool, "error": str | None, "data": ...}
"""
from dataclasses import dataclass
from datetime import date, datetime

import aiohttp

from config import HEMIS_URL, TZ

TIMEOUT = aiohttp.ClientTimeout(total=20)


class HemisError(Exception):
    pass


class ApiError(HemisError):
    """HEMIS javob berdi, lekin success=false."""


class LoginError(HemisError):
    """Login yoki parol noto'g'ri."""


class TokenExpired(HemisError):
    """Token eskirgan, foydalanuvchi qayta kirishi kerak."""


@dataclass
class Lesson:
    day: date
    start: str  # "08:30"
    end: str
    pair: str
    subject: str
    room: str
    building: str
    kind: str  # ma'ruza, amaliyot, ...
    teacher: str


def _name(obj, key: str = "name") -> str:
    if isinstance(obj, dict):
        return str(obj.get(key) or "").strip()
    return ""


async def _request(method: str, path: str, token: str | None = None, **kwargs):
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    url = f"{HEMIS_URL}/rest/v1/{path}"
    try:
        async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
            async with session.request(method, url, headers=headers, **kwargs) as resp:
                if resp.status == 401:
                    raise TokenExpired()
                try:
                    body = await resp.json(content_type=None)
                except ValueError:
                    raise HemisError(f"HEMIS noto'g'ri javob qaytardi (HTTP {resp.status})")
    except aiohttp.ClientError as e:
        raise HemisError(f"HEMIS bilan aloqa yo'q: {e}") from e

    if not isinstance(body, dict) or not body.get("success"):
        error = body.get("error") if isinstance(body, dict) else None
        raise ApiError(error or f"HEMIS xatosi (HTTP {resp.status})")
    return body.get("data")


async def login(username: str, password: str) -> str:
    try:
        data = await _request("POST", "auth/login", json={"login": username, "password": password})
    except (ApiError, TokenExpired) as e:
        raise LoginError() from e
    token = (data or {}).get("token")
    if not token:
        raise LoginError()
    return token


async def get_profile(token: str) -> dict:
    data = await _request("GET", "account/me", token) or {}
    return {
        "full_name": str(data.get("full_name") or "").strip(),
        "student_id": str(data.get("student_id_number") or ""),
        "group": _name(data.get("group")),
        "faculty": _name(data.get("faculty")),
        "specialty": _name(data.get("specialty")),
        "level": _name(data.get("level")),
        "semester": _name(data.get("semester")),
        "education_form": _name(data.get("educationForm")),
        "education_type": _name(data.get("educationType")),
        "payment_form": _name(data.get("paymentForm")),
        "status": _name(data.get("studentStatus")),
        "university": str(data.get("university") or "").strip(),
        "gpa": str(data.get("avg_gpa") or "").strip(),
        "image": str(data.get("image") or "").strip(),
    }


async def get_image(url: str) -> bytes | None:
    """Talaba rasmi (HEMIS uni token'siz beradi)."""
    try:
        async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
            async with session.get(url) as resp:
                if resp.status == 200 and resp.content_type.startswith("image/"):
                    return await resp.read()
    except aiohttp.ClientError:
        pass
    return None


@dataclass
class Absence:
    day: date
    subject: str
    kind: str
    pair: str
    start: str
    teacher: str
    hours: int
    excused: bool


async def get_attendance(token: str) -> list[Absence]:
    """Joriy semestrda qoldirilgan darslar (har bir yozuv bitta dars)."""
    data = await _request("GET", "education/attendance", token) or []
    result = []
    for item in data:
        if not isinstance(item, dict) or not item.get("lesson_date"):
            continue
        excused_hours = int(item.get("absent_on") or 0)
        unexcused_hours = int(item.get("absent_off") or 0)
        pair = item.get("lessonPair") or {}
        result.append(Absence(
            day=datetime.fromtimestamp(int(item["lesson_date"]), TZ).date(),
            subject=_name(item.get("subject")) or "Noma'lum fan",
            kind=_name(item.get("trainingType")),
            pair=_name(pair) or str(pair.get("code") or ""),
            start=str(pair.get("start_time") or "")[:5],
            teacher=_name(item.get("employee")),
            hours=excused_hours + unexcused_hours,
            excused=bool(item.get("explicable")) or (excused_hours > 0 and not unexcused_hours),
        ))
    result.sort(key=lambda a: a.day, reverse=True)
    return result


@dataclass
class Gpa:
    year: str     # "2025-2026"
    level: str    # "3-kurs"
    gpa: str      # "3.64"
    credits: int  # shu yilgacha jami
    subjects: int
    debts: int    # qarzdor fanlar soni


async def get_gpa(token: str) -> list[Gpa]:
    """O'quv yillari bo'yicha GPA, eng yangisi birinchi.

    Fanlar bo'yicha baholar (education/subject-list) SamDU'da hamma joyda 0 qaytadi,
    shuning uchun faqat GPA olinadi.
    """
    data = await _request("GET", "education/gpa-list", token) or []
    result = []
    for item in data:
        if not isinstance(item, dict) or not item.get("gpa"):
            continue
        year = item.get("educationYear") or {}
        result.append(Gpa(
            year=_name(year) or str(year.get("code") or ""),
            level=_name(item.get("level")),
            gpa=str(item["gpa"]).strip(),
            credits=int(float(item.get("credit_sum") or 0)),
            subjects=int(item.get("subjects") or 0),
            debts=int(item.get("debt_subjects") or 0),
        ))
    result.sort(key=lambda g: g.year, reverse=True)
    return result


def _parse_lesson(item: dict) -> Lesson | None:
    ts = item.get("lesson_date")
    pair = item.get("lessonPair") or {}
    if not ts or not pair.get("start_time"):
        return None
    auditorium = item.get("auditorium") or {}
    return Lesson(
        day=datetime.fromtimestamp(int(ts), TZ).date(),
        start=str(pair.get("start_time"))[:5],
        end=str(pair.get("end_time") or "")[:5],
        pair=_name(pair) or str(pair.get("code") or ""),
        subject=_name(item.get("subject")) or "Noma'lum fan",
        room=_name(auditorium),
        building=_name(auditorium.get("building")),
        kind=_name(item.get("trainingType")),
        teacher=_name(item.get("employee")),
    )


@dataclass
class Task:
    id: int
    subject_id: int
    subject: str
    name: str
    deadline: datetime
    max_ball: int
    attempt_limit: int
    attempt_count: int
    submitted: bool
    teacher: str
    files: list[tuple[str, str]]  # (nomi, url) — domla yuklagan topshiriq fayllari


def _parse_task(item: dict) -> Task | None:
    if not item.get("id") or not item.get("deadline"):
        return None
    status = item.get("taskStatus") or {}
    attempts = int(item.get("attempt_count") or 0)
    return Task(
        id=int(item["id"]),
        subject_id=int((item.get("subject") or {}).get("id") or 0),
        subject=_name(item.get("subject")) or "Noma'lum fan",
        name=str(item.get("name") or "").strip() or "Topshiriq",
        deadline=datetime.fromtimestamp(int(item["deadline"]), TZ),
        max_ball=int(item.get("max_ball") or 0),
        attempt_limit=int(item.get("attempt_limit") or 0),
        attempt_count=attempts,
        # "11" = Berildi (hali yuklanmagan), boshqalari: Topshirdi, Baholandi ...
        submitted=str(status.get("code") or "11") != "11" or attempts > 0,
        teacher=_name(item.get("employee")),
        files=[(str(f.get("name") or "fayl"), str(f["url"]))
               for f in item.get("files") or [] if isinstance(f, dict) and f.get("url")],
    )


async def get_tasks(token: str) -> list[Task]:
    """Joriy semestrdagi barcha fanlarning topshiriqlari."""
    semesters = await _request("GET", "education/semesters", token) or []
    current = next((s for s in semesters if isinstance(s, dict) and s.get("current")), None)
    if not current:
        return []
    code = str(current.get("code"))
    subjects = await _request("GET", "education/subjects", token) or []
    tasks = []
    for s in subjects:
        if not isinstance(s, dict) or str(s.get("_semester")) != code or not s.get("tasks_count"):
            continue
        subject_id = (s.get("subject") or {}).get("id")
        data = await _request("GET", "education/subject", token,
                              params={"subject": subject_id, "semester": code}) or {}
        tasks += [t for t in (_parse_task(i) for i in data.get("tasks") or [] if isinstance(i, dict)) if t]
    tasks.sort(key=lambda t: t.deadline)
    return tasks


async def get_schedule(token: str) -> list[Lesson]:
    """Parametrsiz so'rov semestrning e'lon qilingan barcha haftalarini qaytaradi."""
    data = await _request("GET", "education/schedule", token) or []
    if isinstance(data, dict):  # ba'zi versiyalarda {"items": [...]}
        data = data.get("items") or []
    lessons = [l for l in (_parse_lesson(i) for i in data if isinstance(i, dict)) if l]
    lessons.sort(key=lambda l: (l.day, l.start))
    return lessons
