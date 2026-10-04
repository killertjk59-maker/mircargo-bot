import datetime
import sqlite3
import uuid

import config
from domain import lifecycle_from_status, normalize_phone

_conn = None


def get_conn():
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA foreign_keys = ON")
        _conn.execute("PRAGMA busy_timeout = 5000")
    return _conn


def now():
    # Keep the existing database's naive UTC ISO format for compatibility.
    return datetime.datetime.utcnow().isoformat()


def _warehouse_defaults(brand):
    return {
        "warehouse_address_tj": f"🏭 Адреси анбор дар Хитой:\n\n{brand} Warehouse\nYiwu, Zhejiang, China\n(Адреси пурраро аз admin гиред)",
        "warehouse_address_ru": f"🏭 Адрес склада в Китае:\n\n{brand} Warehouse\nYiwu, Zhejiang, China\n(Полный адрес уточните у администратора)",
        "warehouse_address_en": f"🏭 China warehouse address:\n\n{brand} Warehouse\nYiwu, Zhejiang, China\n(Ask admin for full address)",
    }


def init_db():
    conn = get_conn()
    # Explicit BEGIN also makes SQLite DDL part of the transaction.
    # The migration is additive: no tables or data are dropped.
    with conn:
        conn.execute("BEGIN")
        conn.execute("""
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
        conn.execute("""
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            phone TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL
        )""")
        conn.execute("""
        CREATE TABLE IF NOT EXISTS account_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL REFERENCES customers(id),
            entry_type TEXT NOT NULL CHECK(entry_type IN ('charge', 'payment')),
            amount_minor INTEGER NOT NULL CHECK(amount_minor > 0),
            note TEXT NOT NULL DEFAULT '',
            created_by INTEGER NOT NULL,
            operation_key TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL
        )""")
        conn.execute("""
        CREATE TABLE IF NOT EXISTS tracks (
            track_code TEXT PRIMARY KEY,
            customer_name TEXT,
            status TEXT,
            auto_status INTEGER DEFAULT 1,
            received_date TEXT,
            estimated_days TEXT,
            arrival_city TEXT,
            created_at TEXT,
            cargo_status TEXT NOT NULL DEFAULT 'warehouse',
            arrived_at TEXT,
            collected_at TEXT,
            customer_id INTEGER REFERENCES customers(id),
            archived INTEGER NOT NULL DEFAULT 0
        )""")
        columns = {row['name'] for row in conn.execute("PRAGMA table_info(tracks)")}
        added_lifecycle = "cargo_status" not in columns
        additions = {
            "cargo_status": "TEXT NOT NULL DEFAULT 'warehouse'",
            "arrived_at": "TEXT",
            "collected_at": "TEXT",
            "customer_id": "INTEGER REFERENCES customers(id)",
            "archived": "INTEGER NOT NULL DEFAULT 0",
        }
        for name, declaration in additions.items():
            if name not in columns:
                conn.execute(f"ALTER TABLE tracks ADD COLUMN {name} {declaration}")
        if added_lifecycle:
            for track in conn.execute("SELECT track_code, status, auto_status FROM tracks").fetchall():
                lifecycle = "warehouse" if track["auto_status"] else lifecycle_from_status(track["status"] or "")
                conn.execute("UPDATE tracks SET cargo_status=? WHERE track_code=?",
                             (lifecycle, track["track_code"]))
            # No arrival/collection date or recipient is invented for legacy records.

        conn.execute("""
        CREATE TABLE IF NOT EXISTS user_track_views (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            track_code TEXT,
            viewed_at TEXT
        )""")
        conn.execute("""
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
        conn.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_account_entries_customer ON account_entries(customer_id, id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tracks_lifecycle ON tracks(cargo_status, archived)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tracks_customer ON tracks(customer_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_user_views_user ON user_track_views(user_id, track_code)")

        defaults = {
            "forbidden_items_tj": "🔋 Батарея ва акумулятор\n🧴 Моеъҳои хатарнок\n🔥 Маводи оташгир ва тарканда\n💊 Дору ва маводи мухаддир\n🔫 Силоҳ ва лавозимоти он\n💵 Пул ва асъор",
            "forbidden_items_ru": "🔋 Батареи и аккумуляторы\n🧴 Опасные жидкости\n🔥 Легковоспламеняющиеся и взрывоопасные вещества\n💊 Лекарства и наркотические вещества\n🔫 Оружие и боеприпасы\n💵 Деньги и валюта",
            "forbidden_items_en": "🔋 Batteries and accumulators\n🧴 Hazardous liquids\n🔥 Flammable and explosive materials\n💊 Drugs and medicines\n🔫 Weapons and ammunition\n💵 Cash and currency",
            "price_per_kg": config.DEFAULT_PRICE_PER_KG,
            "payment_number": config.PAYMENT_NUMBER,
            **_warehouse_defaults(config.BOT_NAME),
        }
        if config.INSTAGRAM_URL:
            defaults["instagram_url"] = config.INSTAGRAM_URL
        for key, value in defaults.items():
            conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?,?)", (key, value))
        # Rebrand only untouched stock addresses, never an admin's custom address.
        for brand in ("Mirsaid Cargo", "TAJWAY CARGO", "Tajway Cargo"):
            for key, old_value in _warehouse_defaults(brand).items():
                conn.execute("UPDATE settings SET value=? WHERE key=? AND value=?",
                             (defaults[key], key, old_value))


# ---------- Settings ----------

def get_setting(key, default=""):
    row = get_conn().execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(key, value):
    conn = get_conn()
    with conn:
        conn.execute("INSERT INTO settings (key, value) VALUES (?,?) "
                     "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))


# ---------- Users ----------

def get_user(user_id):
    return get_conn().execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()


def upsert_user_basic(user_id, username):
    conn = get_conn()
    with conn:
        conn.execute("""INSERT INTO users (user_id, username, created_at)
                         VALUES (?,?,?)
                         ON CONFLICT(user_id) DO UPDATE SET username=excluded.username""",
                     (user_id, username, now()))


def register_user(user_id, full_name, phone):
    conn = get_conn()
    with conn:
        conn.execute("UPDATE users SET full_name=?, phone=?, registered=1 WHERE user_id=?",
                     (full_name, phone, user_id))


def set_language(user_id, lang):
    if lang not in ("tj", "ru", "en"):
        return
    conn = get_conn()
    with conn:
        conn.execute("UPDATE users SET language=? WHERE user_id=?", (lang, user_id))


def get_language(user_id):
    user = get_user(user_id)
    return user["language"] if user and user["language"] in ("tj", "ru", "en") else "tj"


def all_registered_users():
    return get_conn().execute("SELECT * FROM users WHERE registered=1 AND banned=0").fetchall()


def all_users():
    return get_conn().execute("SELECT * FROM users ORDER BY created_at DESC").fetchall()


def set_banned(user_id, banned):
    conn = get_conn()
    with conn:
        conn.execute("UPDATE users SET banned=? WHERE user_id=?", (1 if banned else 0, user_id))


def user_count():
    return get_conn().execute("SELECT COUNT(*) c FROM users WHERE registered=1").fetchone()["c"]


# ---------- Tracks ----------

def add_track(track_code, customer_name, arrival_city, estimated_days, status):
    conn = get_conn()
    timestamp = now()
    with conn:
        conn.execute("""INSERT INTO tracks (track_code, customer_name, status, auto_status,
                         received_date, estimated_days, arrival_city, created_at)
                         VALUES (?,?,?,1,?,?,?,?)
                         ON CONFLICT(track_code) DO UPDATE SET
                            customer_name=CASE WHEN tracks.cargo_status='collected'
                                               THEN tracks.customer_name ELSE excluded.customer_name END,
                            estimated_days=excluded.estimated_days,
                            arrival_city=excluded.arrival_city,
                            archived=0""",
                     (track_code.upper(), customer_name, status, timestamp, estimated_days, arrival_city, timestamp))
        # A duplicate import updates metadata, not lifecycle or accounting history.


def get_track(track_code, include_archived=False):
    query = "SELECT * FROM tracks WHERE track_code=?"
    if not include_archived:
        query += " AND archived=0"
    return get_conn().execute(query, (track_code.upper(),)).fetchone()


def set_track_lifecycle(track_code, lifecycle):
    if lifecycle not in ("warehouse", "on_way", "arrived"):
        raise ValueError("Барои додани бор тугмаи «Додани бор ба муштарӣ»-ро истифода баред.")
    conn = get_conn()
    with conn:
        track = get_track(track_code)
        if not track:
            raise ValueError("Ин трек-код ёфт нашуд.")
        if track["cargo_status"] == "collected":
            raise ValueError("Ин бор аллакай ба муштарӣ дода шудааст.")
        changed = track["cargo_status"] != lifecycle or bool(track["auto_status"])
        conn.execute("""UPDATE tracks SET cargo_status=?, status=?, auto_status=0,
                         arrived_at=CASE WHEN ?='arrived' THEN COALESCE(arrived_at, ?) ELSE arrived_at END
                         WHERE track_code=?""",
                     (lifecycle, lifecycle, lifecycle, now(), track["track_code"]))
    return changed


def update_track_status(track_code, status, auto_status=0):
    lifecycle = lifecycle_from_status(status)
    if lifecycle in ("warehouse", "on_way", "arrived") and not auto_status:
        return set_track_lifecycle(track_code, lifecycle)
    if lifecycle == "collected":
        raise ValueError("Барои сабти гирифтани бор аввал муштариро интихоб кунед.")
    conn = get_conn()
    with conn:
        track = get_track(track_code)
        if not track:
            raise ValueError("Ин трек-код ёфт нашуд.")
        if track["cargo_status"] == "collected":
            raise ValueError("Ин бор аллакай ба муштарӣ дода шудааст.")
        conn.execute("UPDATE tracks SET status=?, auto_status=?, cargo_status=? WHERE track_code=?",
                     (status, auto_status, "warehouse" if auto_status else "custom", track["track_code"]))
    return True


def update_track_field(track_code, field, value):
    if field == "status":
        return update_track_status(track_code, value)
    if field not in ("customer_name", "arrival_city", "estimated_days"):
        raise ValueError("Майдони нодуруст.")
    conn = get_conn()
    with conn:
        conn.execute(f"UPDATE tracks SET {field}=? WHERE track_code=? AND archived=0", (value, track_code.upper()))


def collect_track(track_code, customer_id):
    """One confirmed handover per track, with an explicitly chosen recipient."""
    conn = get_conn()
    with conn:
        customer = get_customer(customer_id)
        track = get_track(track_code)
        if not customer or not track:
            raise ValueError("Муштарӣ ё трек ёфт нашуд.")
        if track["cargo_status"] == "collected":
            return False
        if track["cargo_status"] != "arrived":
            raise ValueError("Аввал расидани борро сабт кунед («Борҳо расиданд»).")
        cursor = conn.execute("""UPDATE tracks SET cargo_status='collected', status='collected',
                                 auto_status=0, collected_at=?, customer_id=?, customer_name=?
                                 WHERE track_code=? AND cargo_status='arrived' AND archived=0""",
                              (now(), customer_id, customer["full_name"], track["track_code"]))
    return cursor.rowcount == 1


def delete_track(track_code):
    # Archive instead of destroying the history used by the statistics.
    conn = get_conn()
    with conn:
        cursor = conn.execute("UPDATE tracks SET archived=1 WHERE track_code=? AND archived=0", (track_code.upper(),))
    return cursor.rowcount == 1


def all_tracks(limit=50):
    return get_conn().execute("SELECT * FROM tracks WHERE archived=0 ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()


def log_view(user_id, track_code):
    conn = get_conn()
    with conn:
        conn.execute("INSERT INTO user_track_views (user_id, track_code, viewed_at) VALUES (?,?,?)",
                     (user_id, track_code.upper(), now()))


def user_tracks(user_id):
    return get_conn().execute("""SELECT DISTINCT t.* FROM tracks t
                                JOIN user_track_views v ON v.track_code = t.track_code
                                WHERE v.user_id=? AND t.archived=0 ORDER BY t.created_at DESC""", (user_id,)).fetchall()


# ---------- Customer accounts (independent of tracks) ----------

_ACCOUNT_QUERY = """
SELECT c.*,
       COALESCE(SUM(CASE WHEN e.entry_type='charge' THEN e.amount_minor ELSE 0 END), 0) AS total_charges,
       COALESCE(SUM(CASE WHEN e.entry_type='payment' THEN e.amount_minor ELSE 0 END), 0) AS total_payments,
       COALESCE(SUM(CASE WHEN e.entry_type='charge' THEN e.amount_minor ELSE -e.amount_minor END), 0) AS balance,
       MAX(e.created_at) AS last_entry_at
FROM customers c LEFT JOIN account_entries e ON e.customer_id=c.id
GROUP BY c.id
"""


def create_customer(full_name, phone):
    full_name = full_name.strip()
    if not full_name or len(full_name) > 100 or any(ord(char) < 32 for char in full_name):
        raise ValueError("Номи муштарӣ бояд аз 1–100 аломат бошад.")
    phone = normalize_phone(phone)
    conn = get_conn()
    try:
        with conn:
            cursor = conn.execute("INSERT INTO customers (full_name, phone, created_at) VALUES (?,?,?)",
                                  (full_name, phone, now()))
    except sqlite3.IntegrityError:
        existing = conn.execute("SELECT id FROM customers WHERE phone=?", (phone,)).fetchone()
        if existing:
            raise ValueError(f"Ин телефон аллакай сабт шудааст: муштарии #{existing['id']}.") from None
        raise
    return cursor.lastrowid


def get_customer(customer_id):
    return get_conn().execute("SELECT * FROM customers WHERE id=?", (customer_id,)).fetchone()


def customer_account(customer_id):
    return get_conn().execute(f"WITH accounts AS ({_ACCOUNT_QUERY}) SELECT * FROM accounts WHERE id=?", (customer_id,)).fetchone()


def customer_count():
    return get_conn().execute("SELECT COUNT(*) FROM customers").fetchone()[0]


def customer_accounts(limit=8, offset=0, debtors_only=False):
    query = f"WITH accounts AS ({_ACCOUNT_QUERY}) SELECT * FROM accounts"
    if debtors_only:
        query += " WHERE balance > 0 ORDER BY balance DESC, id"
    else:
        query += " ORDER BY id DESC"
    if limit is not None:
        query += " LIMIT ? OFFSET ?"
        return get_conn().execute(query, (limit, offset)).fetchall()
    return get_conn().execute(query).fetchall()


def account_summary():
    return dict(get_conn().execute(f"""WITH accounts AS ({_ACCOUNT_QUERY})
        SELECT COUNT(*) AS customers_total,
               COALESCE(SUM(total_charges),0) AS total_charges,
               COALESCE(SUM(total_payments),0) AS total_payments,
               COALESCE(SUM(CASE WHEN balance>0 THEN balance ELSE 0 END),0) AS outstanding,
               COALESCE(SUM(CASE WHEN balance<0 THEN -balance ELSE 0 END),0) AS credit,
               COALESCE(SUM(CASE WHEN balance>0 THEN 1 ELSE 0 END),0) AS debtors_count
        FROM accounts""").fetchone())


def record_account_entry(customer_id, entry_type, amount_minor, note, created_by, operation_key=None):
    if entry_type not in ("charge", "payment"):
        raise ValueError("Навъи амалиёт нодуруст аст.")
    if type(amount_minor) is not int or not 0 < amount_minor <= 99_999_999_999:
        raise ValueError("Маблағи амалиёт нодуруст аст.")
    if len(note) > 500 or any(ord(char) < 32 and char not in "\n\t" for char in note):
        raise ValueError("Шарҳ бояд то 500 аломат бошад.")
    if not get_customer(customer_id):
        raise ValueError("Муштарӣ ёфт нашуд.")
    operation_key = operation_key or uuid.uuid4().hex
    conn = get_conn()
    with conn:
        cursor = conn.execute("""INSERT INTO account_entries
            (customer_id, entry_type, amount_minor, note, created_by, operation_key, created_at)
            VALUES (?,?,?,?,?,?,?) ON CONFLICT(operation_key) DO NOTHING""",
                              (customer_id, entry_type, amount_minor, note, created_by, operation_key, now()))
    return cursor.rowcount == 1


def customer_entries(customer_id, limit=10):
    return get_conn().execute("SELECT * FROM account_entries WHERE customer_id=? ORDER BY id DESC LIMIT ?",
                             (customer_id, limit)).fetchall()


# ---------- Deliveries ----------

def create_delivery(user_id, track_code, address, name, phone):
    conn = get_conn()
    with conn:
        cursor = conn.execute("""INSERT INTO deliveries (user_id, track_code, address, name, phone, status, created_at)
                         VALUES (?,?,?,?,?, 'waiting_payment', ?)""",
                              (user_id, track_code.upper(), address, name, phone, now()))
    return cursor.lastrowid


def set_delivery_status(delivery_id, status, expected_status=None):
    if status not in ("waiting_payment", "pending_review", "confirmed", "rejected"):
        raise ValueError("Мақоми доставка нодуруст аст.")
    conn = get_conn()
    query = "UPDATE deliveries SET status=? WHERE id=?"
    params = [status, delivery_id]
    if expected_status is not None:
        query += " AND status=?"
        params.append(expected_status)
    with conn:
        cursor = conn.execute(query, params)
    return cursor.rowcount == 1


def get_delivery(delivery_id):
    return get_conn().execute("SELECT * FROM deliveries WHERE id=?", (delivery_id,)).fetchone()


def pending_deliveries():
    return get_conn().execute("SELECT * FROM deliveries WHERE status='pending_review' ORDER BY created_at").fetchall()


# ---------- Statistics ----------

def get_statistics():
    conn = get_conn()
    stats = dict(conn.execute("""SELECT COUNT(*) AS users_total,
        COALESCE(SUM(registered=1),0) AS registered_users,
        COALESCE(SUM(banned=1),0) AS banned_users FROM users""").fetchone())
    stats.update(dict(conn.execute("""SELECT COUNT(*) AS searches,
        COUNT(DISTINCT user_id) AS search_users FROM user_track_views""").fetchone()))
    timestamp = now()
    cutoff = (datetime.datetime.utcnow() - datetime.timedelta(days=config.AUTO_STATUS_DAYS)).isoformat()
    stats.update(dict(conn.execute("""WITH cargo AS (
        SELECT *, CASE
            WHEN cargo_status IN ('arrived','collected','custom') THEN cargo_status
            WHEN auto_status=1 AND COALESCE(received_date,created_at,?)<=? THEN 'on_way'
            WHEN auto_status=1 THEN 'warehouse'
            ELSE cargo_status END AS effective_status FROM tracks)
        SELECT COUNT(*) AS tracks_total,
            COALESCE(SUM(archived=0),0) AS active_tracks,
            COALESCE(SUM(archived=1),0) AS archived_tracks,
            COALESCE(SUM(archived=0 AND effective_status='warehouse'),0) AS warehouse,
            COALESCE(SUM(archived=0 AND effective_status='on_way'),0) AS on_way,
            COALESCE(SUM(archived=0 AND effective_status='arrived'),0) AS awaiting_collection,
            COALESCE(SUM(archived=0 AND effective_status='custom'),0) AS other_status,
            COALESCE(SUM(arrived_at IS NOT NULL OR cargo_status IN ('arrived','collected')),0) AS arrived_total,
            COALESCE(SUM(cargo_status='collected'),0) AS collected,
            COUNT(DISTINCT CASE WHEN cargo_status='collected' THEN customer_id END) AS collectors,
            COALESCE(SUM(cargo_status='collected' AND customer_id IS NULL),0) AS unassigned_collected
        FROM cargo""", (timestamp, cutoff)).fetchone()))
    stats.update(account_summary())
    stats.update(dict(conn.execute("""SELECT COUNT(*) AS deliveries_total,
        COALESCE(SUM(status='waiting_payment'),0) AS deliveries_waiting,
        COALESCE(SUM(status='pending_review'),0) AS deliveries_pending,
        COALESCE(SUM(status='confirmed'),0) AS deliveries_confirmed,
        COALESCE(SUM(status='rejected'),0) AS deliveries_rejected FROM deliveries""").fetchone()))
    return stats
