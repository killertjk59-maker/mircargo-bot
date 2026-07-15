import sqlite3
import datetime
import config

_conn = None


def get_conn():
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
    return _conn


def now():
    return datetime.datetime.utcnow().isoformat()


def init_db():
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        full_name TEXT,
        phone TEXT,
        language TEXT DEFAULT 'tj',
        registered INTEGER DEFAULT 0,
        banned INTEGER DEFAULT 0,
        created_at TEXT
    )""")
    c.execute("""
    CREATE TABLE IF NOT EXISTS tracks (
        track_code TEXT PRIMARY KEY,
        customer_name TEXT,
        status TEXT,
        auto_status INTEGER DEFAULT 1,
        received_date TEXT,
        estimated_days TEXT,
        arrival_city TEXT,
        created_at TEXT
    )""")
    c.execute("""
    CREATE TABLE IF NOT EXISTS user_track_views (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        track_code TEXT,
        viewed_at TEXT
    )""")
    c.execute("""
    CREATE TABLE IF NOT EXISTS deliveries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        track_code TEXT,
        address TEXT,
        name TEXT,
        phone TEXT,
        status TEXT DEFAULT 'waiting_payment',
        created_at TEXT
    )""")
    c.execute("""
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )""")
    conn.commit()

    # Танзимоти пешфарз
    defaults = {
        "forbidden_items_tj": "🔋 Батарея ва акумулятор\n🧴 Моеъҳои хатарнок\n🔥 Маводи оташгир ва тарканда\n💊 Дору ва маводи мухаддир\n🔫 Силоҳ ва лавозимоти он\n💵 Пул ва асъор",
        "forbidden_items_ru": "🔋 Батареи и аккумуляторы\n🧴 Опасные жидкости\n🔥 Легковоспламеняющиеся и взрывоопасные вещества\n💊 Лекарства и наркотические вещества\n🔫 Оружие и боеприпасы\n💵 Деньги и валюта",
        "forbidden_items_en": "🔋 Batteries and accumulators\n🧴 Hazardous liquids\n🔥 Flammable and explosive materials\n💊 Drugs and medicines\n🔫 Weapons and ammunition\n💵 Cash and currency",
        "warehouse_address_tj": "🏭 Адреси анбор дар Хитой:\n\nMirsaid Cargo Warehouse\nYiwu, Zhejiang, China\n(Адреси пурраро аз admin гиред)",
        "warehouse_address_ru": "🏭 Адрес склада в Китае:\n\nMirsaid Cargo Warehouse\nYiwu, Zhejiang, China\n(Полный адрес уточните у администратора)",
        "warehouse_address_en": "🏭 China warehouse address:\n\nMirsaid Cargo Warehouse\nYiwu, Zhejiang, China\n(Ask admin for full address)",
        "price_per_kg": config.DEFAULT_PRICE_PER_KG,
        "payment_number": config.PAYMENT_NUMBER,
    }
    for k, v in defaults.items():
        c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?,?)", (k, v))
    conn.commit()


# ---------- Settings ----------

def get_setting(key, default=""):
    conn = get_conn()
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(key, value):
    conn = get_conn()
    conn.execute("INSERT INTO settings (key, value) VALUES (?,?) "
                 "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
    conn.commit()


# ---------- Users ----------

def get_user(user_id):
    conn = get_conn()
    return conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()


def upsert_user_basic(user_id, username):
    conn = get_conn()
    conn.execute("""INSERT INTO users (user_id, username, created_at)
                     VALUES (?,?,?)
                     ON CONFLICT(user_id) DO UPDATE SET username=excluded.username""",
                 (user_id, username, now()))
    conn.commit()


def register_user(user_id, full_name, phone):
    conn = get_conn()
    conn.execute("""UPDATE users SET full_name=?, phone=?, registered=1 WHERE user_id=?""",
                 (full_name, phone, user_id))
    conn.commit()


def set_language(user_id, lang):
    conn = get_conn()
    conn.execute("UPDATE users SET language=? WHERE user_id=?", (lang, user_id))
    conn.commit()


def get_language(user_id):
    u = get_user(user_id)
    if u and u["language"]:
        return u["language"]
    return "tj"


def all_registered_users():
    conn = get_conn()
    return conn.execute("SELECT * FROM users WHERE registered=1 AND banned=0").fetchall()


def all_users():
    conn = get_conn()
    return conn.execute("SELECT * FROM users ORDER BY created_at DESC").fetchall()


def set_banned(user_id, banned):
    conn = get_conn()
    conn.execute("UPDATE users SET banned=? WHERE user_id=?", (1 if banned else 0, user_id))
    conn.commit()


def user_count():
    conn = get_conn()
    return conn.execute("SELECT COUNT(*) c FROM users WHERE registered=1").fetchone()["c"]


# ---------- Tracks ----------

def add_track(track_code, customer_name, arrival_city, estimated_days, status):
    conn = get_conn()
    conn.execute("""INSERT INTO tracks (track_code, customer_name, status, auto_status,
                     received_date, estimated_days, arrival_city, created_at)
                     VALUES (?,?,?,1,?,?,?,?)
                     ON CONFLICT(track_code) DO UPDATE SET
                        customer_name=excluded.customer_name,
                        status=excluded.status,
                        estimated_days=excluded.estimated_days,
                        arrival_city=excluded.arrival_city""",
                 (track_code.upper(), customer_name, status, now(), estimated_days, arrival_city, now()))
    conn.commit()


def get_track(track_code):
    conn = get_conn()
    return conn.execute("SELECT * FROM tracks WHERE track_code=?", (track_code.upper(),)).fetchone()


def update_track_status(track_code, status, auto_status=0):
    conn = get_conn()
    conn.execute("UPDATE tracks SET status=?, auto_status=? WHERE track_code=?",
                 (status, auto_status, track_code.upper()))
    conn.commit()


def update_track_field(track_code, field, value):
    conn = get_conn()
    if field not in ("customer_name", "arrival_city", "estimated_days", "status"):
        return
    conn.execute(f"UPDATE tracks SET {field}=? WHERE track_code=?", (value, track_code.upper()))
    conn.commit()


def delete_track(track_code):
    conn = get_conn()
    conn.execute("DELETE FROM tracks WHERE track_code=?", (track_code.upper(),))
    conn.commit()


def all_tracks(limit=50):
    conn = get_conn()
    return conn.execute("SELECT * FROM tracks ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()


def log_view(user_id, track_code):
    conn = get_conn()
    conn.execute("INSERT INTO user_track_views (user_id, track_code, viewed_at) VALUES (?,?,?)",
                 (user_id, track_code.upper(), now()))
    conn.commit()


def user_tracks(user_id):
    conn = get_conn()
    return conn.execute("""SELECT DISTINCT t.* FROM tracks t
                            JOIN user_track_views v ON v.track_code = t.track_code
                            WHERE v.user_id=? ORDER BY t.created_at DESC""", (user_id,)).fetchall()


# ---------- Deliveries ----------

def create_delivery(user_id, track_code, address, name, phone):
    conn = get_conn()
    cur = conn.execute("""INSERT INTO deliveries (user_id, track_code, address, name, phone, status, created_at)
                     VALUES (?,?,?,?,?, 'waiting_payment', ?)""",
                 (user_id, track_code.upper(), address, name, phone, now()))
    conn.commit()
    return cur.lastrowid


def set_delivery_status(delivery_id, status):
    conn = get_conn()
    conn.execute("UPDATE deliveries SET status=? WHERE id=?", (status, delivery_id))
    conn.commit()


def get_delivery(delivery_id):
    conn = get_conn()
    return conn.execute("SELECT * FROM deliveries WHERE id=?", (delivery_id,)).fetchone()


def pending_deliveries():
    conn = get_conn()
    return conn.execute("SELECT * FROM deliveries WHERE status='pending_review' ORDER BY created_at").fetchall()
