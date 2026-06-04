import aiosqlite
import os
from config import DATABASE_PATH, BASE_DIR

DB_PATH = os.path.join(BASE_DIR, DATABASE_PATH)

async def get_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA foreign_keys=ON")
    return db

async def init_db():
    db = await get_db()
    try:
        await db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            real_name TEXT NOT NULL,
            department TEXT NOT NULL,
            phone TEXT DEFAULT '',
            is_active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS user_roles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            role TEXT NOT NULL CHECK(role IN ('admin','applicant','dept_supervisor','studio_manager','executor')),
            UNIQUE(user_id, role)
        );

        CREATE TABLE IF NOT EXISTS meeting_types (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            is_active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            applicant_id INTEGER NOT NULL REFERENCES users(id),
            department TEXT NOT NULL,
            contact TEXT NOT NULL,
            meeting_topic TEXT NOT NULL,
            meeting_type_id INTEGER NOT NULL REFERENCES meeting_types(id),
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            remarks TEXT DEFAULT '',
            status TEXT NOT NULL DEFAULT 'pending'
                CHECK(status IN ('pending','dept_approved','dept_rejected','studio_approved','studio_rejected','assigned','completed','reported')),
            assigned_executor_id INTEGER REFERENCES users(id),
            created_at TEXT DEFAULT (datetime('now','localtime')),
            updated_at TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS approval_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            application_id INTEGER NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
            approver_id INTEGER NOT NULL REFERENCES users(id),
            approver_role TEXT NOT NULL,
            stage TEXT NOT NULL CHECK(stage IN ('dept','studio')),
            action TEXT NOT NULL CHECK(action IN ('approve','reject')),
            comment TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS post_event_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            application_id INTEGER NOT NULL UNIQUE REFERENCES applications(id),
            items_returned TEXT NOT NULL,
            cleanliness TEXT NOT NULL,
            damage TEXT DEFAULT '',
            score REAL NOT NULL CHECK(score >= 0 AND score <= 10.0),
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS report_photos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            report_id INTEGER NOT NULL REFERENCES post_event_reports(id) ON DELETE CASCADE,
            category TEXT NOT NULL CHECK(category IN ('returned','cleanliness','damage')),
            file_path TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS departments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            is_active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            application_id INTEGER NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
            from_user_id INTEGER NOT NULL REFERENCES users(id),
            target_stage TEXT NOT NULL,
            message TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS system_config (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            description TEXT DEFAULT ''
        );
        """)
        await db.commit()
    finally:
        await db.close()


async def get_config(key: str, default: str = "") -> str:
    """Get a system config value by key, returning default if not found."""
    db = await get_db()
    try:
        cur = await db.execute("SELECT value FROM system_config WHERE key=?", (key,))
        row = await cur.fetchone()
        return row["value"] if row else default
    finally:
        await db.close()


async def set_config(key: str, value: str, description: str = "") -> None:
    """Set a system config value (insert or update)."""
    db = await get_db()
    try:
        await db.execute(
            "INSERT INTO system_config (key, value, description) VALUES (?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, description=excluded.description",
            (key, value, description),
        )
        await db.commit()
    finally:
        await db.close()


async def seed_db():
    import bcrypt
    db = await get_db()
    try:
        cur = await db.execute("SELECT COUNT(*) FROM users")
        count = (await cur.fetchone())[0]
        if count > 0:
            return

        pw = bcrypt.hashpw("123456".encode(), bcrypt.gensalt()).decode()
        users = [
            ("admin", pw, "系统管理员", "信息中心", "13800000000"),
            ("zhangsan", pw, "张三", "小学部", "13800000001"),
            ("lisi", pw, "李四", "小学部", "13800000002"),
            ("wangwu", pw, "王五", "中学部", "13800000003"),
            ("zhaoliu", pw, "赵六", "信息中心", "13800000004"),
        ]
        for u in users:
            await db.execute(
                "INSERT INTO users (username, password_hash, real_name, department, phone) VALUES (?,?,?,?,?)",
                u
            )

        roles = [
            (1, "admin"),
            (2, "applicant"), (2, "dept_supervisor"),
            (3, "applicant"),
            (4, "studio_manager"),
            (5, "executor"),
        ]
        for r in roles:
            await db.execute("INSERT INTO user_roles (user_id, role) VALUES (?,?)", r)

        depts = ["小学部", "中学部", "高中部", "国际部", "信息中心", "教务处", "总务处"]
        for d in depts:
            await db.execute("INSERT OR IGNORE INTO departments (name) VALUES (?)", (d,))

        types = ["教研会议", "家长会", "学生活动", "教师培训", "行政会议", "公开课"]
        for t in types:
            await db.execute("INSERT INTO meeting_types (name) VALUES (?)", (t,))

        # Seed system config defaults
        configs = [
            ("max_booking_minutes", "180", "预约最长时长（分钟），默认180分钟（3小时）"),
            ("unit_name", "", "单位名称，显示在系统标题前"),
        ]
        for k, v, desc in configs:
            await db.execute(
                "INSERT OR IGNORE INTO system_config (key, value, description) VALUES (?, ?, ?)",
                (k, v, desc),
            )

        await db.commit()
    finally:
        await db.close()
