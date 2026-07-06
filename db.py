# -*- coding: utf-8 -*-
"""Захираи маълумот бо SQLite — пешрафти истифодабаранда."""
import sqlite3
import os
import threading

DB_PATH = os.path.join(os.path.dirname(__file__), "chembot.db")
_lock = threading.Lock()


def _connect():
    return sqlite3.connect(DB_PATH)


def init_db():
    with _lock, _connect() as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                first_name TEXT,
                first_seen TEXT DEFAULT CURRENT_TIMESTAMP
            )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS activity (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                action TEXT,
                detail TEXT,
                ts TEXT DEFAULT CURRENT_TIMESTAMP
            )"""
        )
        conn.commit()


def ensure_user(user_id, first_name=""):
    with _lock, _connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO users (user_id, first_name) VALUES (?, ?)",
            (user_id, first_name),
        )
        conn.commit()


def log_action(user_id, action, detail=""):
    with _lock, _connect() as conn:
        conn.execute(
            "INSERT INTO activity (user_id, action, detail) VALUES (?, ?, ?)",
            (user_id, action, detail),
        )
        conn.commit()


def get_progress(user_id):
    with _lock, _connect() as conn:
        cur = conn.execute(
            "SELECT action, COUNT(*) FROM activity WHERE user_id=? GROUP BY action",
            (user_id,),
        )
        rows = cur.fetchall()
    return dict(rows)


ACTION_LABELS = {
    "table_view": "Дидани элементҳо",
    "method_view": "Мутолиаи усулҳо",
    "ai_example": "Мисоли AI гирифта",
    "calc_use": "Истифодаи ҳисобкунак",
    "ai_question": "Саволи AI пурсида",
}
