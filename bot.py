# -*- coding: utf-8 -*-
import time
import datetime
import requests

import config
import database as db
from texts import t
import keyboards as kb

# ============ Telegram API helpers ============

def api(method, params=None, files=None):
    url = f"{config.API_URL}/{method}"
    try:
        r = requests.post(url, json=params if not files else None,
                           data=params if files else None, files=files, timeout=30)
        return r.json()
    except Exception as e:
        print(f"[API ERROR] {method}: {e}")
        return {}


def send_message(chat_id, text, reply_markup=None):
    params = {"chat_id": chat_id, "text": text}
    if reply_markup:
        params["reply_markup"] = reply_markup
    return api("sendMessage", params)


def answer_callback(callback_id, text=None, show_alert=False):
    params = {"callback_query_id": callback_id}
    if text:
        params["text"] = text
        params["show_alert"] = show_alert
    return api("answerCallbackQuery", params)


def get_updates(offset):
    r = api("getUpdates", {"offset": offset, "timeout": 30})
    return r.get("result", [])


# ============ In-memory state ============

USER_STATE = {}          # user_id -> {"action": str, "data": {}}
FORWARD_MAP = {}         # (admin_chat_id, message_id) -> user_id  (for contact-admin replies)


def set_state(user_id, action, data=None):
    USER_STATE[user_id] = {"action": action, "data": data or {}}


def clear_state(user_id):
    USER_STATE.pop(user_id, None)


def get_state(user_id):
    return USER_STATE.get(user_id)


# ============ Helpers ============

def is_admin(user_id):
    return user_id in config.ADMIN_IDS


def lang_of(user_id):
    return db.get_language(user_id)


def notify_admins(text, reply_markup=None):
    sent = []
    for admin_id in config.ADMIN_IDS:
        res = send_message(admin_id, text, reply_markup)
        sent.append((admin_id, res))
    return sent


def track_status_display(track, lang):
    if track["auto_status"]:
        received = datetime.datetime.fromisoformat(track["received_date"])
        days_passed = (datetime.datetime.utcnow() - received).days
        if days_passed >= config.AUTO_STATUS_DAYS:
            return t("status_on_way", lang)
        return t("status_warehouse", lang)
    return track["status"]


def format_track(track, lang):
    return t("track_result", lang,
              code=track["track_code"],
              status=track_status_display(track, lang),
              date=track["received_date"][:10],
              days=track["estimated_days"] or config.DEFAULT_ESTIMATED_DAYS,
              city=track["arrival_city"] or config.DEFAULT_ARRIVAL_CITY)


def show_main_menu(chat_id, user_id, text_key="main_menu"):
    lang = lang_of(user_id)
    send_message(chat_id, t(text_key, lang), kb.main_menu_reply(lang, is_admin(user_id)))


# ============ Registration flow ============

def start_registration(chat_id, user_id, username):
    db.upsert_user_basic(user_id, username)
    lang = lang_of(user_id)
    send_message(chat_id, t("ask_contact", lang), kb.contact_request_kb(lang))
    set_state(user_id, "reg_wait_contact")


def handle_contact(message, user_id):
    contact = message.get("contact")
    if not contact:
        return
    phone = contact.get("phone_number", "")
    set_state(user_id, "reg_wait_name", {"phone": phone})
    lang = lang_of(user_id)
    send_message(message["chat"]["id"], t("ask_name", lang))


def finish_registration(chat_id, user_id, name, phone):
    db.register_user(user_id, name, phone)
    lang = lang_of(user_id)
    send_message(chat_id, t("registered_ok", lang))
    clear_state(user_id)
    show_main_menu(chat_id, user_id)


# ============ Track search ============

def do_track_search(chat_id, user_id, code):
    lang = lang_of(user_id)
    code = code.strip().upper()
    track = db.get_track(code)
    if not track:
        send_message(chat_id, t("track_not_found", lang, admin=config.ADMIN_USERNAME))
        return
    db.log_view(user_id, code)
    send_message(chat_id, format_track(track, lang))


# ============ Admin: add tracks (bulk) ============

def parse_bulk_tracks(text):
    """
    Ҳар хат = як трек.
    Формат: CODE  ё  CODE|Ном|Рӯзҳо|Шаҳр
    """
    results = []
    for line in text.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split("|")]
        code = parts[0].upper()
        name = parts[1] if len(parts) > 1 and parts[1] else code
        days = parts[2] if len(parts) > 2 and parts[2] else config.DEFAULT_ESTIMATED_DAYS
        city = parts[3] if len(parts) > 3 and parts[3] else config.DEFAULT_ARRIVAL_CITY
        results.append((code, name, days, city))
    return results


def handle_admin_add_tracks(chat_id, admin_id, text):
    lang = lang_of(admin_id)
    items = parse_bulk_tracks(text)
    if not items:
        send_message(chat_id, "❌ Ягон трек-код ёфт нашуд.")
        return
    added = []
    for code, name, days, city in items:
        db.add_track(code, name, city, days, t("status_warehouse", "tj"))
        added.append(code)
    send_message(chat_id, "✅ Трек-кодҳои зерин илова шуданд:\n" + "\n".join(f"• {c}" for c in added))
    clear_state(admin_id)


# ============ Delivery flow ============

def start_delivery(chat_id, user_id):
    lang = lang_of(user_id)
    send_message(chat_id, t("delivery_intro", lang, admin=config.ADMIN_USERNAME), kb.cancel_reply_kb(lang))
    set_state(user_id, "delivery_track")


def process_delivery_step(message, user_id, state):
    chat_id = message["chat"]["id"]
    lang = lang_of(user_id)
    text = message.get("text", "").strip()
    action = state["action"]
    data = state["data"]

    if text == t("btn_cancel", lang):
        clear_state(user_id)
        send_message(chat_id, t("cancel", lang))
        show_main_menu(chat_id, user_id)
        return

    if action == "delivery_track":
        data["track_code"] = text.upper()
        set_state(user_id, "delivery_address", data)
        send_message(chat_id, t("delivery_ask_address", lang))

    elif action == "delivery_address":
        data["address"] = text
        set_state(user_id, "delivery_name", data)
        send_message(chat_id, t("delivery_ask_name", lang))

    elif action == "delivery_name":
        data["name"] = text
        set_state(user_id, "delivery_phone", data)
        send_message(chat_id, t("delivery_ask_phone", lang))

    elif action == "delivery_phone":
        data["phone"] = text
        delivery_id = db.create_delivery(user_id, data["track_code"], data["address"],
                                          data["name"], data["phone"])
        payment_number = db.get_setting("payment_number", config.PAYMENT_NUMBER)
        send_message(chat_id, t("delivery_payment_instructions", lang, number=payment_number),
                     kb.paid_button_kb(lang, delivery_id))
        clear_state(user_id)
        show_main_menu(chat_id, user_id)


# ============ Calculator ============

def process_calc(chat_id, user_id, text):
    lang = lang_of(user_id)
    try:
        kg = float(text.replace(",", "."))
    except ValueError:
        send_message(chat_id, t("calc_invalid", lang))
        return
    price = float(db.get_setting("price_per_kg", config.DEFAULT_PRICE_PER_KG))
    total = round(kg * price, 2)
    send_message(chat_id, t("calc_result", lang, kg=kg, price=price, total=total))
    clear_state(user_id)
    show_main_menu(chat_id, user_id)


# ============ Contact admin (two-way chat) ============

def process_contact_admin_msg(message, user_id):
    chat_id = message["chat"]["id"]
    lang = lang_of(user_id)
    text = message.get("text", "")
    u = db.get_user(user_id)
    uname = f"@{u['username']}" if u and u["username"] else "-"
    header = f"📩 Паём аз {u['full_name'] if u else user_id} ({uname})\nID: {user_id}\nТел: {u['phone'] if u else '-'}\n\n{text}"
    for admin_id in config.ADMIN_IDS:
        res = send_message(admin_id, header)
        msg_id = res.get("result", {}).get("message_id")
        if msg_id:
            FORWARD_MAP[(admin_id, msg_id)] = user_id
    send_message(chat_id, t("contact_admin_sent", lang))
    clear_state(user_id)
    show_main_menu(chat_id, user_id)


def process_admin_reply(message, admin_id):
    """Агар admin ба паёми forward-шуда reply кунад, ба корбар мефиристем."""
    reply_to = message.get("reply_to_message")
    if not reply_to:
        return False
    key = (admin_id, reply_to.get("message_id"))
    target_user = FORWARD_MAP.get(key)
    if not target_user:
        return False
    lang = lang_of(target_user)
    text = message.get("text", "")
    send_message(target_user, t("admin_reply_prefix", lang) + text)
    send_message(admin_id, "✅ Ирсол шуд.")
    return True


# ============ Admin panel actions ============

def open_admin_panel(chat_id):
    send_message(chat_id, "⚙️ Admin Panel", kb.admin_panel_kb())


def handle_admin_callback(callback, admin_id):
    data = callback["data"]
    chat_id = callback["message"]["chat"]["id"]
    cq_id = callback["id"]

    if data == "adm_panel":
        answer_callback(cq_id)
        open_admin_panel(chat_id)
        return

    if data == "adm_add_track":
        answer_callback(cq_id)
        set_state(admin_id, "adm_add_track_input")
        send_message(chat_id, "✏️ Трек-кодҳоро фиристед (ҳар хат = як код).\n\n"
                               "Формат:\nCODE\nCODE|Ном|Рӯзҳо|Шаҳр\n\n"
                               "Мисол:\nKH22FF99\nGG22KK|Usmonov|20-25 рӯз|Истаравшан\nJJ32SD")
        return

    if data == "adm_edit_track":
        answer_callback(cq_id)
        set_state(admin_id, "adm_edit_track_select")
        send_message(chat_id, "✏️ Трек-кодеро нависед, ки мехоҳед таҳрир кунед:")
        return

    if data == "adm_del_track":
        answer_callback(cq_id)
        set_state(admin_id, "adm_del_track_input")
        send_message(chat_id, "🗑 Трек-кодеро нависед, ки мехоҳед нест кунед:")
        return

    if data == "adm_list_tracks":
        answer_callback(cq_id)
        tracks = db.all_tracks(30)
        if not tracks:
            send_message(chat_id, "Ҳоло трек нест.")
        else:
            lines = [f"• {tr['track_code']} — {tr['customer_name']}" for tr in tracks]
            send_message(chat_id, "📋 30 трек-коди охирин:\n" + "\n".join(lines))
        return

    if data == "adm_users":
        answer_callback(cq_id)
        users = db.all_users()
        count = db.user_count()
        lines = [f"• {u['full_name'] or '-'} | {u['phone'] or '-'} | id:{u['user_id']}" for u in users[:40]]
        send_message(chat_id, f"👥 Ҳамагӣ сабтшуда: {count}\n\n" + "\n".join(lines))
        return

    if data == "adm_broadcast":
        answer_callback(cq_id)
        set_state(admin_id, "adm_broadcast_input")
        send_message(chat_id, "📢 Паёмеро нависед, ки ба ҳамаи корбарон фиристода мешавад:")
        return

    if data == "adm_edit_forbidden":
        answer_callback(cq_id)
        set_state(admin_id, "adm_edit_forbidden_input")
        send_message(chat_id, "✏️ Матни нави 'борҳои манъшуда'-ро (бо забони тоҷикӣ) нависед:")
        return

    if data == "adm_edit_warehouse":
        answer_callback(cq_id)
        set_state(admin_id, "adm_edit_warehouse_input")
        send_message(chat_id, "✏️ Адреси нави склад (бо забони тоҷикӣ)-ро нависед:")
        return

    if data == "adm_edit_price":
        answer_callback(cq_id)
        set_state(admin_id, "adm_edit_price_input")
        send_message(chat_id, "✏️ Нархи нави 1 кг-ро (рақам, сомонӣ) нависед:")
        return

    if data == "adm_pending_deliveries":
        answer_callback(cq_id)
        pend = db.pending_deliveries()
        if not pend:
            send_message(chat_id, "Дархости боқимонда нест.")
        for d in pend:
            u = db.get_user(d["user_id"])
            text = (f"🚚 Дархости #{d['id']}\nТрек: {d['track_code']}\n"
                    f"Ном: {d['name']}\nТел: {d['phone']}\nАдрес: {d['address']}\n"
                    f"Корбар: {u['full_name'] if u else d['user_id']}")
            send_message(chat_id, text, kb.admin_delivery_review_kb(d["id"]))
        return

    if data.startswith("etf_"):
        # etf_<field>_<code>
        answer_callback(cq_id)
        _, field, code = data.split("_", 2)
        field_map = {"name": "customer_name", "status": "status", "days": "estimated_days", "city": "arrival_city"}
        set_state(admin_id, "adm_edit_track_value", {"field": field_map[field], "code": code})
        send_message(chat_id, f"✏️ Қимати нави '{field}' барои {code}-ро нависед:")
        return

    if data.startswith("delok_") or data.startswith("delno_"):
        delivery_id = int(data.split("_", 1)[1])
        d = db.get_delivery(delivery_id)
        if not d:
            answer_callback(cq_id, "Дархост ёфт нашуд.")
            return
        target_lang = lang_of(d["user_id"])
        if data.startswith("delok_"):
            db.set_delivery_status(delivery_id, "confirmed")
            send_message(d["user_id"], t("delivery_confirmed", target_lang))
            answer_callback(cq_id, "Тасдиқ шуд ✅")
        else:
            db.set_delivery_status(delivery_id, "rejected")
            send_message(d["user_id"], t("delivery_rejected", target_lang, admin=config.ADMIN_USERNAME))
            answer_callback(cq_id, "Рад шуд ❌")
        return

    answer_callback(cq_id)


def handle_admin_text_state(message, admin_id, state):
    chat_id = message["chat"]["id"]
    text = message.get("text", "")
    action = state["action"]
    data = state["data"]

    if action == "adm_add_track_input":
        handle_admin_add_tracks(chat_id, admin_id, text)

    elif action == "adm_edit_track_select":
        code = text.strip().upper()
        track = db.get_track(code)
        if not track:
            send_message(chat_id, "❌ Ин трек-код ёфт нашуд.")
            clear_state(admin_id)
        else:
            send_message(chat_id, f"Трек: {code}\nКадом майдонро таҳрир мекунед?", kb.admin_edit_track_field_kb(code))
            clear_state(admin_id)

    elif action == "adm_edit_track_value":
        db.update_track_field(data["code"], data["field"], text)
        if data["field"] == "status":
            db.update_track_status(data["code"], text, auto_status=0)
        send_message(chat_id, "✅ Нав карда шуд.")
        clear_state(admin_id)

    elif action == "adm_del_track_input":
        code = text.strip().upper()
        db.delete_track(code)
        send_message(chat_id, f"🗑 Трек {code} нест карда шуд.")
        clear_state(admin_id)

    elif action == "adm_broadcast_input":
        users = db.all_registered_users()
        sent = 0
        for u in users:
            send_message(u["user_id"], f"📢 {text}")
            sent += 1
            time.sleep(0.05)
        send_message(chat_id, f"✅ Ба {sent} корбар фиристода шуд.")
        clear_state(admin_id)

    elif action == "adm_edit_forbidden_input":
        db.set_setting("forbidden_items_tj", text)
        send_message(chat_id, "✅ Матни борҳои манъшуда нав карда шуд.")
        clear_state(admin_id)

    elif action == "adm_edit_warehouse_input":
        db.set_setting("warehouse_address_tj", text)
        send_message(chat_id, "✅ Адреси склад нав карда шуд.")
        clear_state(admin_id)

    elif action == "adm_edit_price_input":
        try:
            float(text.replace(",", "."))
            db.set_setting("price_per_kg", text.replace(",", "."))
            send_message(chat_id, "✅ Нарх нав карда шуд.")
        except ValueError:
            send_message(chat_id, "❌ Рақами нодуруст.")
        clear_state(admin_id)


# ============ Callback query dispatcher ============

def handle_callback_query(callback):
    user_id = callback["from"]["id"]
    data = callback["data"]
    chat_id = callback["message"]["chat"]["id"]
    cq_id = callback["id"]

    if data.startswith("lang_"):
        lang = data.split("_", 1)[1]
        db.set_language(user_id, lang)
        answer_callback(cq_id)
        send_message(chat_id, t("language_set", lang))
        show_main_menu(chat_id, user_id)
        return

    if data.startswith("paid_"):
        delivery_id = int(data.split("_", 1)[1])
        db.set_delivery_status(delivery_id, "pending_review")
        lang = lang_of(user_id)
        answer_callback(cq_id)
        send_message(chat_id, t("delivery_waiting_confirm", lang))
        d = db.get_delivery(delivery_id)
        u = db.get_user(user_id)
        admin_text = (f"🚚 Дархости доставка #{delivery_id}\n"
                       f"Трек: {d['track_code']}\nНом: {d['name']}\nТел: {d['phone']}\n"
                       f"Адрес: {d['address']}\nКорбар: {u['full_name'] if u else user_id}\n\n"
                       f"Пардохт ба {db.get_setting('payment_number', config.PAYMENT_NUMBER)} гуфта шудааст. Санҷед.")
        notify_admins(admin_text, kb.admin_delivery_review_kb(delivery_id))
        return

    if data.startswith("adm_") or data.startswith("etf_") or data.startswith("delok_") or data.startswith("delno_"):
        if is_admin(user_id):
            handle_admin_callback(callback, user_id)
        else:
            answer_callback(cq_id)
        return

    answer_callback(cq_id)


# ============ Message dispatcher ============

def handle_message(message):
    if "from" not in message:
        return
    user_id = message["from"]["id"]
    chat_id = message["chat"]["id"]
    username = message["from"].get("username", "")
    text = message.get("text", "")

    db.upsert_user_basic(user_id, username)
    u = db.get_user(user_id)

    # --- admin reply-to-forwarded-message shortcut ---
    if is_admin(user_id) and message.get("reply_to_message"):
        if process_admin_reply(message, user_id):
            return

    # --- commands ---
    if text == "/start":
        clear_state(user_id)
        if u and u["registered"]:
            show_main_menu(chat_id, user_id)
        else:
            start_registration(chat_id, user_id, username)
        return

    if text == "/language":
        lang = lang_of(user_id)
        send_message(chat_id, t("choose_language", lang), kb.language_inline_kb())
        return

    if text == "/admin" and is_admin(user_id):
        open_admin_panel(chat_id)
        return

    if not u or not u["registered"]:
        if message.get("contact"):
            handle_contact(message, user_id)
            return
        state = get_state(user_id)
        if state and state["action"] == "reg_wait_name":
            finish_registration(chat_id, user_id, text, state["data"].get("phone", ""))
            return
        lang = lang_of(user_id)
        send_message(chat_id, t("not_registered", lang))
        start_registration(chat_id, user_id, username)
        return

    lang = lang_of(user_id)
    state = get_state(user_id)

    # --- state machine (registered users) ---
    if state:
        action = state["action"]

        if is_admin(user_id) and action.startswith("adm_"):
            handle_admin_text_state(message, user_id, state)
            return

        if action == "search_track":
            clear_state(user_id)
            do_track_search(chat_id, user_id, text)
            show_main_menu(chat_id, user_id)
            return

        if action == "calc_kg":
            process_calc(chat_id, user_id, text)
            return

        if action == "contact_admin_msg":
            process_contact_admin_msg(message, user_id)
            return

        if action.startswith("delivery_"):
            process_delivery_step(message, user_id, state)
            return

    # --- reply keyboard buttons ---
    if text == t("btn_search_track", lang):
        set_state(user_id, "search_track")
        send_message(chat_id, t("ask_track_code", lang))
        return

    if text == t("btn_my_tracks", lang):
        tracks = db.user_tracks(user_id)
        if not tracks:
            send_message(chat_id, t("my_tracks_empty", lang))
        else:
            send_message(chat_id, t("my_tracks_title", lang))
            for tr in tracks:
                send_message(chat_id, format_track(tr, lang))
        return

    if text == t("btn_forbidden", lang):
        content = db.get_setting(f"forbidden_items_{lang}", db.get_setting("forbidden_items_tj"))
        send_message(chat_id, "⛔ " + content)
        return

    if text == t("btn_calc", lang):
        set_state(user_id, "calc_kg")
        send_message(chat_id, t("calc_ask_kg", lang))
        return

    if text == t("btn_warehouse", lang):
        content = db.get_setting(f"warehouse_address_{lang}", db.get_setting("warehouse_address_tj"))
        send_message(chat_id, content)
        return

    if text == t("btn_contact_admin", lang):
        set_state(user_id, "contact_admin_msg")
        send_message(chat_id, t("contact_admin_intro", lang))
        return

    if text == t("btn_delivery", lang):
        start_delivery(chat_id, user_id)
        return

    if text == t("btn_language", lang):
        send_message(chat_id, t("choose_language", lang), kb.language_inline_kb())
        return

    if text == "⚙️ Admin Panel" and is_admin(user_id):
        open_admin_panel(chat_id)
        return

    # --- default: treat as track code search ---
    if text and not text.startswith("/"):
        do_track_search(chat_id, user_id, text)
        return


# ============ Main loop ============

def main():
    print("TAJWAY CARGO BOT — старт...")
    db.init_db()
    offset = 0
    while True:
        try:
            updates = get_updates(offset)
            for upd in updates:
                offset = upd["update_id"] + 1
                if "message" in upd:
                    handle_message(upd["message"])
                elif "callback_query" in upd:
                    handle_callback_query(upd["callback_query"])
        except Exception as e:
            print(f"[LOOP ERROR] {e}")
            time.sleep(3)


if __name__ == "__main__":
    main()
