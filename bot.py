# -*- coding: utf-8 -*-
"""
Super Chemistry Bot — MVP
Функсияҳо: Ҷадвали даврии кӯҳна (8 гурӯҳ) + Тарзи ҳалли масъалаҳо + Ҳисобкунаки
массаи молярӣ + AI муаллим (Groq) + Пешрафти истифодабаранда (SQLite).

Stack: faqat requests (Termux-мутобиқ, бе Rust-компонент), SQLite, long polling.
"""
import os
import time
import logging
import requests

import db
from elements_data import GROUPS, elements_in_group, get_element
from methods_data import METHODS, METHOD_ORDER
from calculators import molar_mass, FormulaError
import groq_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("chembot")

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

USER_STATE = {}  # user_id -> "waiting_formula" | "waiting_ai" | None


def api_call(method, payload=None, retries=3):
    url = f"{API_URL}/{method}"
    for attempt in range(retries):
        try:
            resp = requests.post(url, json=payload or {}, timeout=35)
            if resp.status_code == 429:
                time.sleep(2 ** attempt)
                continue
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as e:
            log.warning("API call %s failed (attempt %d): %s", method, attempt + 1, e)
            time.sleep(1.5 * (attempt + 1))
    return None


def send_message(chat_id, text, reply_markup=None, parse_mode="Markdown"):
    payload = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    return api_call("sendMessage", payload)


def edit_message(chat_id, message_id, text, reply_markup=None, parse_mode="Markdown"):
    payload = {"chat_id": chat_id, "message_id": message_id, "text": text, "parse_mode": parse_mode}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    return api_call("editMessageText", payload)


def answer_callback(callback_id, text=None):
    payload = {"callback_query_id": callback_id}
    if text:
        payload["text"] = text
    return api_call("answerCallbackQuery", payload)


def kb(rows):
    return {"inline_keyboard": rows}


def main_menu_kb():
    return kb([
        [{"text": "📊 Ҷадвали даврӣ", "callback_data": "menu_table"}],
        [{"text": "📐 Тарзи ҳалли масъалаҳо", "callback_data": "menu_methods"}],
        [{"text": "🧮 Ҳисобкунаки массаи молярӣ", "callback_data": "menu_calc"}],
        [{"text": "🤖 AI Муаллим", "callback_data": "menu_ai"}],
        [{"text": "📈 Пешрафти ман", "callback_data": "menu_progress"}],
    ])


def back_kb(target="menu_main"):
    return kb([[{"text": "⬅️ Бозгашт", "callback_data": target}]])


def table_groups_kb():
    rows, row = [], []
    for g in GROUPS:
        row.append({"text": f"Гурӯҳи {g}", "callback_data": f"grp_{g}"})
        if len(row) == 2:
            rows.append(row); row = []
    if row:
        rows.append(row)
    rows.append([{"text": "⬅️ Бозгашт", "callback_data": "menu_main"}])
    return kb(rows)


def group_elements_kb(roman):
    els = elements_in_group(roman)
    rows, row = [], []
    for e in els:
        row.append({"text": f"{e['symbol']} ({e['period']}-давра)", "callback_data": f"el_{e['num']}"})
        if len(row) == 2:
            rows.append(row); row = []
    if row:
        rows.append(row)
    rows.append([{"text": "⬅️ Гурӯҳҳо", "callback_data": "menu_table"}])
    return kb(rows)


def methods_menu_kb():
    rows = [[{"text": METHODS[k]["title"], "callback_data": f"method_{k}"}] for k in METHOD_ORDER]
    rows.append([{"text": "⬅️ Бозгашт", "callback_data": "menu_main"}])
    return kb(rows)


def method_detail_kb(key):
    return kb([
        [{"text": "✨ Мисоли нави AI", "callback_data": f"aiex_{key}"}],
        [{"text": "⬅️ Ҳамаи усулҳо", "callback_data": "menu_methods"}],
    ])


WELCOME = (
    "🧪 *Хуш омадед ба Super Chemistry Bot!*\n\n"
    "Дар ин бот шумо метавонед:\n"
    "• Ҷадвали даврии кӯҳнаро (8 гурӯҳ) омӯзед\n"
    "• Тарзи ҳалли масъалаҳои химиявиро қадам ба қадам ёд гиред\n"
    "• Массаи молярии моддаро ҳисоб кунед\n"
    "• Аз AI муаллим савол пурсед\n\n"
    "Аз менюи зер интихоб кунед 👇"
)


def element_card(e):
    return (
        f"🔬 *{e['name']}* ({e['symbol']})\n\n"
        f"Рақами атомӣ: {e['num']}\n"
        f"Массаи атомӣ: {e['mass']}\n"
        f"Давра: {e['period']}\n"
        f"Гурӯҳ (кӯҳна): {e['group']}"
    )


def handle_start(chat_id, user):
    db.ensure_user(user["id"], user.get("first_name", ""))
    send_message(chat_id, WELCOME, reply_markup=main_menu_kb())


def handle_text(chat_id, user, text):
    state = USER_STATE.get(user["id"])

    if text == "/start":
        handle_start(chat_id, user)
        return
    if text == "/help":
        send_message(chat_id, WELCOME, reply_markup=main_menu_kb())
        return

    if state == "waiting_formula":
        USER_STATE[user["id"]] = None
        try:
            total, breakdown = molar_mass(text)
            db.log_action(user["id"], "calc_use", text)
            msg = f"🧮 Формула: *{text}*\n\n{breakdown}\n\n*M ≈ {total:.3f} г/моль*"
        except FormulaError as e:
            msg = f"❌ {e}\n\nМисол: H2SO4, Ca(OH)2, Al2(SO4)3"
        send_message(chat_id, msg, reply_markup=back_kb())
        return

    if state == "waiting_ai":
        USER_STATE[user["id"]] = None
        send_message(chat_id, "🤔 Фикр карда истодаам...")
        answer = groq_client.ask_teacher(text)
        db.log_action(user["id"], "ai_question", text[:100])
        send_message(chat_id, answer, reply_markup=back_kb())
        return

    send_message(chat_id, "Лутфан аз менюи зер интихоб кунед 👇", reply_markup=main_menu_kb())


def handle_callback(chat_id, message_id, user, data, callback_id):
    answer_callback(callback_id)
    db.ensure_user(user["id"], user.get("first_name", ""))

    if data == "menu_main":
        edit_message(chat_id, message_id, WELCOME, reply_markup=main_menu_kb())

    elif data == "menu_table":
        db.log_action(user["id"], "table_view", "menu")
        edit_message(chat_id, message_id, "📊 *Ҷадвали даврии кӯҳна*\n\nГурӯҳро интихоб кунед:", reply_markup=table_groups_kb())

    elif data.startswith("grp_"):
        roman = data.split("_", 1)[1]
        edit_message(chat_id, message_id, f"📊 *Гурӯҳи {roman}*\n\nЭлементро интихоб кунед:", reply_markup=group_elements_kb(roman))

    elif data.startswith("el_"):
        num = data.split("_", 1)[1]
        e = get_element(num)
        if e:
            edit_message(chat_id, message_id, element_card(e), reply_markup=back_kb("menu_table"))

    elif data == "menu_methods":
        edit_message(chat_id, message_id, "📐 *Тарзи ҳалли масъалаҳо*\n\nКатегорияро интихоб кунед:", reply_markup=methods_menu_kb())

    elif data.startswith("method_"):
        key = data.split("_", 1)[1]
        m = METHODS.get(key)
        if m:
            db.log_action(user["id"], "method_view", key)
            text = f"*{m['title']}*\n\n{m['algorithm']}\n\n{m['example']}"
            edit_message(chat_id, message_id, text, reply_markup=method_detail_kb(key))

    elif data.startswith("aiex_"):
        key = data.split("_", 1)[1]
        m = METHODS.get(key)
        if m:
            edit_message(chat_id, message_id, "✨ AI мисоли нав тартиб дода истодааст...")
            example = groq_client.generate_example(m["title"])
            db.log_action(user["id"], "ai_example", key)
            text = f"*{m['title']} — Мисоли нав*\n\n{example}"
            send_message(chat_id, text, reply_markup=method_detail_kb(key))

    elif data == "menu_calc":
        USER_STATE[user["id"]] = "waiting_formula"
        edit_message(chat_id, message_id, "🧮 Формулаи моддаро нависед (масалан: `H2SO4`, `Ca(OH)2`, `Al2(SO4)3`):", reply_markup=back_kb())

    elif data == "menu_ai":
        USER_STATE[user["id"]] = "waiting_ai"
        edit_message(chat_id, message_id, "🤖 Саволи худро дар бораи химия нависед — ман кӯшиш мекунам ба забони содда ҳал кунам:", reply_markup=back_kb())

    elif data == "menu_progress":
        progress = db.get_progress(user["id"])
        if not progress:
            text = "📈 Шумо ҳанӯз фаъолият надоштаед. Аз менюи асосӣ сар кунед!"
        else:
            lines = [f"• {db.ACTION_LABELS.get(k, k)}: {v}" for k, v in progress.items()]
            text = "📈 *Пешрафти шумо:*\n\n" + "\n".join(lines)
        edit_message(chat_id, message_id, text, reply_markup=back_kb())


def run():
    if not BOT_TOKEN:
        raise SystemExit("TELEGRAM_BOT_TOKEN дар муҳити система ёфт нашуд. Дар .env илова кунед.")

    db.init_db()
    log.info("Super Chemistry Bot оғоз шуд...")

    offset = 0
    while True:
        result = api_call("getUpdates", {"offset": offset, "timeout": 30})
        if not result or not result.get("ok"):
            time.sleep(2)
            continue

        for update in result.get("result", []):
            offset = update["update_id"] + 1
            try:
                if "message" in update and "text" in update["message"]:
                    msg = update["message"]
                    handle_text(msg["chat"]["id"], msg["from"], msg["text"])
                elif "callback_query" in update:
                    cq = update["callback_query"]
                    handle_callback(cq["message"]["chat"]["id"], cq["message"]["message_id"], cq["from"], cq["data"], cq["id"])
            except Exception:
                log.exception("Хатогӣ ҳангоми коркарди update")


if __name__ == "__main__":
    run()
