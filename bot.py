# -*- coding: utf-8 -*-
import time
import datetime
import uuid
import requests

import config
import database as db
from texts import t
import keyboards as kb
import reports
from domain import (CARGO_STATUS_KEYS, format_money, normalize_instagram_url,
                    normalize_track_code, parse_money)

# ============ Telegram API helpers ============

def api(method, params=None, files=None):
    url = f"{config.API_URL}/{method}"
    try:
        r = requests.post(url, json=params if not files else None,
                           data=params if files else None, files=files, timeout=40 if method == "getUpdates" else 30)
        return r.json()
    except Exception as e:
        print(f"[API ERROR] {method}: {type(e).__name__}")
        return {}


def send_message(chat_id, text, reply_markup=None):
    params = {"chat_id": chat_id, "text": text}
    if reply_markup:
        params["reply_markup"] = reply_markup
    return api("sendMessage", params)


def send_document(chat_id, filename, content, caption=None):
    params = {"chat_id": chat_id}
    if caption:
        params["caption"] = caption
    return api("sendDocument", params, files={"document": (filename, content, "text/csv")})


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


def admin_contact(lang):
    return config.ADMIN_USERNAME or t("admin_contact_fallback", lang)


def track_status_display(track, lang):
    lifecycle = track["cargo_status"]
    if lifecycle in ("arrived", "collected"):
        return t(CARGO_STATUS_KEYS[lifecycle], lang)
    if track["auto_status"]:
        try:
            received = datetime.datetime.fromisoformat(track["received_date"] or track["created_at"])
            if received.tzinfo is not None:
                received = received.astimezone(datetime.timezone.utc).replace(tzinfo=None)
            days_passed = (datetime.datetime.utcnow() - received).days
        except (TypeError, ValueError):
            days_passed = 0
        return t("status_on_way" if days_passed >= config.AUTO_STATUS_DAYS else "status_warehouse", lang)
    if lifecycle in CARGO_STATUS_KEYS:
        return t(CARGO_STATUS_KEYS[lifecycle], lang)
    return track["status"] or "—"


def format_track(track, lang):
    return t("track_result", lang,
              code=track["track_code"],
              status=track_status_display(track, lang),
              date=(track["received_date"] or "—")[:10],
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
        send_message(chat_id, t("track_not_found", lang, admin=admin_contact(lang)))
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
    try:
        items = parse_bulk_tracks(text)
        for code, name, days, city in items:
            normalize_track_code(code)
    except ValueError as error:
        send_message(chat_id, f"❌ {error}")
        return
    if not items:
        send_message(chat_id, "❌ Ягон трек-код ёфт нашуд.")
        return
    added = []
    for code, name, days, city in items:
        db.add_track(code, name, city, days, t("status_warehouse", "tj"))
        if code not in added:
            added.append(code)
    send_long_message(chat_id, "✅ Трек-кодҳо илова/нав шуданд (мақоми қаблӣ нигоҳ дошта шуд):\n" + "\n".join(f"• {c}" for c in added))
    clear_state(admin_id)


# ============ Delivery flow ============

def start_delivery(chat_id, user_id):
    lang = lang_of(user_id)
    send_message(chat_id, t("delivery_intro", lang, admin=admin_contact(lang)), kb.cancel_reply_kb(lang))
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


# ============ Tezcargo: Instagram, statistics and customer accounts ============

PAGE_SIZE = 8


def send_long_message(chat_id, text, reply_markup=None):
    # Telegram's 4096 limit counts UTF-16 units; emoji may count as two.
    chunks, buffer, units = [], [], 0
    for character in text:
        cost = 2 if ord(character) > 0xFFFF else 1
        if units + cost > 3500:
            chunks.append("".join(buffer))
            buffer, units = [], 0
        buffer.append(character)
        units += cost
    if buffer:
        chunks.append("".join(buffer))
    for index, chunk in enumerate(chunks):
        send_message(chat_id, chunk, reply_markup if index == len(chunks) - 1 else None)


def show_instagram(chat_id, lang):
    value = db.get_setting("instagram_url", config.INSTAGRAM_URL)
    try:
        url = normalize_instagram_url(value)
    except ValueError:
        send_message(chat_id, t("instagram_unavailable", lang))
        return
    send_message(chat_id, t("instagram_intro", lang), kb.instagram_inline_kb(lang, url))


def show_statistics(chat_id):
    send_message(chat_id, reports.statistics_text(db.get_statistics()), {"inline_keyboard": [
        [{"text": "🔄 Навсозии омор", "callback_data": "adm_stats"},
         {"text": "📋 Қарздорон", "callback_data": "adm_debtors"}],
        [{"text": "⬅️ Панели админ", "callback_data": "adm_panel"}],
    ]})


def _page_info(count, page):
    pages = max(1, (count + PAGE_SIZE - 1) // PAGE_SIZE)
    return min(max(0, page), pages - 1), pages


def show_customers(chat_id, page=0):
    count = db.customer_count()
    page, pages = _page_info(count, page)
    accounts = db.customer_accounts(PAGE_SIZE, page * PAGE_SIZE)
    send_message(chat_id, reports.customers_text(accounts, count, page, pages),
                 kb.customer_list_kb(accounts, page, pages))


def show_customer(chat_id, customer_id):
    account = db.customer_account(customer_id)
    if not account:
        send_message(chat_id, "❌ Муштарӣ ёфт нашуд.", kb.back_to_admin_kb())
        return
    send_message(chat_id, reports.customer_text(account), kb.customer_account_kb(customer_id))


def show_debtors(chat_id, page=0):
    summary = db.account_summary()
    page, pages = _page_info(summary['debtors_count'], page)
    accounts = db.customer_accounts(PAGE_SIZE, page * PAGE_SIZE, debtors_only=True)
    send_message(chat_id, reports.debtors_text(accounts, summary, page, pages),
                 kb.debtors_kb(accounts, page, pages))


def start_customer_creation(chat_id, admin_id, context=None):
    set_state(admin_id, "adm_customer_input", context)
    send_message(chat_id, "👤 Муштарии навро нависед:\nНом ва насаб | Телефон\n\n"
                          "Мисол: Али Раҳимов | +992901234567\n"
                          "Ҳар телефон як ҳисоб дорад. Қарз ба муштарӣ тааллуқ дорад, на ба трек.\n"
                          "/cancel — бекор кардан.")


def show_recipients(chat_id, admin_id, page=0):
    state = get_state(admin_id)
    count = db.customer_count()
    page, pages = _page_info(count, page)
    accounts = db.customer_accounts(PAGE_SIZE, page * PAGE_SIZE)
    send_message(chat_id, f"👤 Барои бори {state['data']['code']} муштарии воқеии гирандаро интихоб кунед.\n"
                          f"Саҳифа {page + 1}/{pages}\n"
                          "Агар муштарӣ ҳоло сабт нашудааст, «Муштарии нав»-ро пахш кунед.",
                 kb.collection_customer_kb(accounts, page, pages, state['data']['token']))


def start_collection(chat_id, admin_id, code):
    track = db.get_track(code)
    if not track:
        raise ValueError("Ин трек-код ёфт нашуд.")
    if track['cargo_status'] == 'collected':
        raise ValueError("Ин бор аллакай ба муштарӣ дода шудааст.")
    if track['cargo_status'] != 'arrived':
        raise ValueError("Аввал расидани борро сабт кунед («Борҳо расиданд»).")
    set_state(admin_id, "adm_collect_pick", {"code": track['track_code'], "token": uuid.uuid4().hex[:12]})
    show_recipients(chat_id, admin_id)


def prompt_collection_confirmation(chat_id, admin_id, code, customer_id, token):
    account = db.customer_account(customer_id)
    if not account:
        raise ValueError("Муштарӣ ёфт нашуд.")
    set_state(admin_id, "adm_collect_confirm", {"code": code, "customer_id": customer_id, "token": token})
    balance = account['balance']
    debt_text = f"⚠️ Қарзи муштарӣ: {format_money(balance)} сомонӣ." if balance > 0 else "✅ Қарзи боқимонда надорад."
    send_message(chat_id, f"📦 Бор: {code}\n👤 Гиранда: {account['full_name']}\n📱 {account['phone']}\n\n"
                          f"{debt_text}\n\n"
                          "Танҳо пас аз воқеан додани бор тасдиқ кунед.\n"
                          "Ин амал пардохтро сабт намекунад ва қарзро кам намекунад.",
                 kb.collection_confirm_kb(token))


def _matching_state(admin_id, token, actions):
    state = get_state(admin_id)
    if state and state['action'] in actions and state['data'].get('token') == token:
        return state
    return None


def handle_accounting_callback(callback, admin_id):
    """Return True if this callback belongs to a Tezcargo admin feature."""
    data = callback['data']
    chat_id = callback['message']['chat']['id']
    cq_id = callback['id']

    if data == 'adm_stats':
        clear_state(admin_id)
        answer_callback(cq_id)
        show_statistics(chat_id)
        return True

    if data == 'adm_customers' or data.startswith('adm_customers_'):
        try:
            page = int(data.removeprefix('adm_customers_')) if data != 'adm_customers' else 0
        except ValueError:
            answer_callback(cq_id)
            return True
        clear_state(admin_id)
        answer_callback(cq_id)
        show_customers(chat_id, page)
        return True

    if data == 'adm_new_customer':
        answer_callback(cq_id)
        start_customer_creation(chat_id, admin_id)
        return True

    if data.startswith(('adm_customer_', 'adm_charge_', 'adm_payment_', 'adm_history_')):
        action, raw_id = data[4:].split('_', 1)
        try:
            customer_id = int(raw_id)
        except ValueError:
            answer_callback(cq_id, "Муштарӣ ёфт нашуд.", True)
            return True
        account = db.customer_account(customer_id)
        if not account:
            answer_callback(cq_id, "Муштарӣ ёфт нашуд.", True)
            return True
        clear_state(admin_id)
        answer_callback(cq_id)
        if action == 'customer':
            show_customer(chat_id, customer_id)
        elif action == 'history':
            send_message(chat_id, reports.history_text(account, db.customer_entries(customer_id)),
                         kb.customer_account_kb(customer_id))
        else:
            entry_type = 'charge' if action == 'charge' else 'payment'
            set_state(admin_id, 'adm_ledger_input', {'customer_id': customer_id, 'entry_type': entry_type})
            label = 'қарз' if entry_type == 'charge' else 'пардохт'
            send_message(chat_id, f"💳 Сабти {label} барои {account['full_name']} (#{customer_id})\n"
                                  f"Тел: {account['phone']}\n\n"
                                  "Маблағро бо сомонӣ нависед; шарҳ ихтиёрӣ аст:\n"
                                  "125.50 | Сабаби амалиёт\n\n"
                                  "Пеш аз сабт тасдиқ мепурсам. /cancel — бекор кардан.")
        return True

    if data.startswith(('adm_ledger_confirm_', 'adm_ledger_cancel_')):
        prefix = 'adm_ledger_confirm_' if data.startswith('adm_ledger_confirm_') else 'adm_ledger_cancel_'
        token = data[len(prefix):]
        state = _matching_state(admin_id, token, ('adm_ledger_confirm',))
        if not state:
            answer_callback(cq_id, "Ин амалиёт аллакай анҷом ёфтааст ё бекор шудааст.", True)
            return True
        entry = state['data']
        if prefix == 'adm_ledger_cancel_':
            clear_state(admin_id)
            answer_callback(cq_id, "Бекор шуд.")
        else:
            try:
                saved = db.record_account_entry(entry['customer_id'], entry['entry_type'], entry['amount_minor'],
                                                entry['note'], admin_id, operation_key=token)
            except ValueError as error:
                answer_callback(cq_id, str(error), True)
                return True
            clear_state(admin_id)
            answer_callback(cq_id, "Сабт шуд ✅" if saved else "Ин амалиёт қаблан сабт шудааст.")
        show_customer(chat_id, entry['customer_id'])
        return True

    if data == 'adm_debtors' or data.startswith('adm_debtors_'):
        try:
            page = int(data.removeprefix('adm_debtors_')) if data != 'adm_debtors' else 0
        except ValueError:
            answer_callback(cq_id)
            return True
        clear_state(admin_id)
        answer_callback(cq_id)
        show_debtors(chat_id, page)
        return True

    if data == 'adm_export_debtors':
        answer_callback(cq_id)
        accounts = db.customer_accounts(limit=None, debtors_only=True)
        total = sum(account['balance'] for account in accounts)
        result = send_document(chat_id, 'Tezcargo-debtors.csv', reports.debtors_csv(accounts),
                               f"📋 Қарздорон: {len(accounts)} | Ҳамагӣ қарз: {format_money(total)} сомонӣ")
        if not result.get('ok'):
            send_message(chat_id, "❌ Файл фиристода нашуд. Боз кӯшиш кунед; рӯйхат дар бот дастрас аст.")
        return True

    if data == 'adm_edit_instagram':
        answer_callback(cq_id)
        set_state(admin_id, 'adm_instagram_input')
        current = db.get_setting('instagram_url', config.INSTAGRAM_URL)
        send_message(chat_id, f"📷 Пайванди ҷорӣ: {current or 'ҳоло гузошта нашудааст'}\n\n"
                              "Пайванди Instagram ё @username-ро нависед:\n"
                              "https://www.instagram.com/your_page/\n\n"
                              "/clear — хориҷ кардани пайванд; /cancel — бекор кардан.")
        return True

    if data == 'adm_arrivals':
        answer_callback(cq_id)
        set_state(admin_id, 'adm_arrivals_input')
        send_message(chat_id, "📦 Трек-кодҳои борҳои воқеан расидаро нависед (ҳар хат як код).\n"
                              "Такроран сабт кардани ҳамон код ҳисобро зиёд намекунад.\n/cancel — бекор кардан.")
        return True

    if data == 'adm_collect':
        answer_callback(cq_id)
        set_state(admin_id, 'adm_collect_input')
        send_message(chat_id, "✅ Трек-коди бореро нависед, ки ба муштарӣ медиҳед.\n"
                              "Аввал бор бояд ҳамчун «Бор расид» сабт шуда бошад.\n/cancel — бекор кардан.")
        return True

    if data.startswith('adm_recipients_') or data.startswith('adm_recipient_'):
        prefix = 'adm_recipients_' if data.startswith('adm_recipients_') else 'adm_recipient_'
        try:
            raw_value, token = data[len(prefix):].split('_', 1)
            value = int(raw_value)
        except ValueError:
            answer_callback(cq_id)
            return True
        state = _matching_state(admin_id, token, ('adm_collect_pick',))
        if not state:
            answer_callback(cq_id, "Гирандаро аз нав интихоб кунед.", True)
            return True
        if prefix == 'adm_recipients_':
            answer_callback(cq_id)
            show_recipients(chat_id, admin_id, value)
        else:
            try:
                prompt_collection_confirmation(chat_id, admin_id, state['data']['code'], value, token)
                answer_callback(cq_id)
            except ValueError as error:
                answer_callback(cq_id, str(error), True)
        return True

    if data.startswith('adm_collect_new_'):
        token = data[len('adm_collect_new_'):]
        state = _matching_state(admin_id, token, ('adm_collect_pick',))
        if not state:
            answer_callback(cq_id, "Ин интихоб дигар фаъол нест.", True)
            return True
        answer_callback(cq_id)
        start_customer_creation(chat_id, admin_id, state['data'].copy())
        return True

    if data.startswith('adm_collect_cancel_'):
        token = data[len('adm_collect_cancel_'):]
        state = _matching_state(admin_id, token, ('adm_collect_pick', 'adm_collect_confirm', 'adm_customer_input'))
        if not state:
            answer_callback(cq_id, "Ин амалиёт дигар фаъол нест.")
            return True
        clear_state(admin_id)
        answer_callback(cq_id, "Бекор шуд.")
        open_admin_panel(chat_id)
        return True

    if data.startswith('adm_collect_confirm_'):
        token = data[len('adm_collect_confirm_'):]
        state = _matching_state(admin_id, token, ('adm_collect_confirm',))
        if not state:
            answer_callback(cq_id, "Ин амалиёт аллакай анҷом ёфтааст ё бекор шудааст.", True)
            return True
        entry = state['data']
        try:
            changed = db.collect_track(entry['code'], entry['customer_id'])
        except ValueError as error:
            answer_callback(cq_id, str(error), True)
            return True
        clear_state(admin_id)
        answer_callback(cq_id, "Бор дода шуд ✅" if changed else "Ин бор қаблан дода шудааст.")
        send_message(chat_id, format_track(db.get_track(entry['code']), lang_of(admin_id)), kb.back_to_admin_kb())
        return True

    if data.startswith('ets_'):
        try:
            lifecycle, token = data[4:].rsplit('_', 1)
        except ValueError:
            answer_callback(cq_id)
            return True
        state = _matching_state(admin_id, token, ('adm_edit_track_value',))
        if not state or state['data'].get('field') != 'status':
            answer_callback(cq_id, "Мақоми трекро аз нав интихоб кунед.", True)
            return True
        code = state['data']['code']
        try:
            if lifecycle == 'collected':
                start_collection(chat_id, admin_id, code)
            else:
                db.set_track_lifecycle(code, lifecycle)
                clear_state(admin_id)
                send_message(chat_id, format_track(db.get_track(code), lang_of(admin_id)), kb.back_to_admin_kb())
            answer_callback(cq_id)
        except ValueError as error:
            answer_callback(cq_id, str(error), True)
        return True

    return False


def handle_accounting_text(message, admin_id, state):
    chat_id = message['chat']['id']
    text = message.get('text', '').strip()
    action, data = state['action'], state['data']

    if action == 'adm_instagram_input':
        try:
            url = '' if text == '/clear' else normalize_instagram_url(text)
        except ValueError as error:
            send_message(chat_id, f"❌ {error}")
            return True
        db.set_setting('instagram_url', url)
        clear_state(admin_id)
        send_message(chat_id, "✅ Пайванди Instagram сабт шуд." if url else "✅ Пайванди Instagram хориҷ шуд.", kb.back_to_admin_kb())
        return True

    if action == 'adm_customer_input':
        parts = [part.strip() for part in text.split('|')]
        if len(parts) != 2:
            send_message(chat_id, "❌ Формат: Ном ва насаб | Телефон\n/cancel — бекор кардан.")
            return True
        try:
            customer_id = db.create_customer(*parts)
        except ValueError as error:
            send_message(chat_id, f"❌ {error}")
            return True
        clear_state(admin_id)
        send_message(chat_id, f"✅ Муштарии #{customer_id} сабт шуд.")
        if data.get('code'):
            prompt_collection_confirmation(chat_id, admin_id, data['code'], customer_id, data['token'])
        else:
            show_customer(chat_id, customer_id)
        return True

    if action == 'adm_ledger_input':
        parts = text.split('|', 1)
        note = parts[1].strip() if len(parts) == 2 else ''
        try:
            amount = parse_money(parts[0])
            if len(note) > 500 or any(ord(char) < 32 and char not in "\n\t" for char in note):
                raise ValueError("Шарҳ бояд то 500 аломати дуруст бошад.")
        except ValueError as error:
            send_message(chat_id, f"❌ {error}")
            return True
        account = db.customer_account(data['customer_id'])
        token = uuid.uuid4().hex
        entry = dict(data, amount_minor=amount, note=note, token=token)
        set_state(admin_id, 'adm_ledger_confirm', entry)
        label = 'Қарз' if data['entry_type'] == 'charge' else 'Пардохт'
        send_message(chat_id, f"🔎 Тасдиқи амалиёт\n👤 {account['full_name']} (#{account['id']})\n"
                              f"📱 {account['phone']}\n{label}: {format_money(amount)} сомонӣ\n"
                              f"Шарҳ: {note or '—'}\n\nҲоло сабт нашудааст. Тасдиқ мекунед?",
                     kb.ledger_confirm_kb(token))
        return True

    if action == 'adm_arrivals_input':
        try:
            codes = list(dict.fromkeys(normalize_track_code(line) for line in text.splitlines() if line.strip()))
            if not codes:
                raise ValueError("Ақаллан як трек-код нависед.")
        except ValueError as error:
            send_message(chat_id, f"❌ {error}")
            return True
        lines = []
        for code in codes:
            try:
                changed = db.set_track_lifecycle(code, 'arrived')
                lines.append(f"{'✅ Расид' if changed else 'ℹ️ Қаблан расида буд'}: {code}")
            except ValueError as error:
                lines.append(f"❌ {code}: {error}")
        clear_state(admin_id)
        send_long_message(chat_id, "📦 Натиҷаи сабти расидани борҳо:\n" + "\n".join(lines), kb.back_to_admin_kb())
        return True

    if action == 'adm_collect_input':
        try:
            start_collection(chat_id, admin_id, text.upper())
        except ValueError as error:
            send_message(chat_id, f"❌ {error}")
        return True

    if action in ('adm_ledger_confirm', 'adm_collect_confirm', 'adm_collect_pick'):
        send_message(chat_id, "Тугмаи интихоб/тасдиқро пахш кунед ё /cancel нависед.")
        return True

    return False


# ============ Admin panel actions ============

def open_admin_panel(chat_id):
    send_message(chat_id, "⚙️ Admin Panel", kb.admin_panel_kb())


def handle_admin_callback(callback, admin_id):
    data = callback["data"]
    chat_id = callback["message"]["chat"]["id"]
    cq_id = callback["id"]

    if handle_accounting_callback(callback, admin_id):
        return

    if data == "adm_panel":
        clear_state(admin_id)
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
        send_message(chat_id, "🗃 Трек-кодеро нависед, ки мехоҳед ба бойгонӣ гузоред (таърих дар омор мемонад):")
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
        state = get_state(admin_id)
        field = data[4:]
        field_map = {"name": "customer_name", "status": "status", "days": "estimated_days", "city": "arrival_city"}
        if not state or state["action"] not in ("adm_edit_track_fields", "adm_edit_track_value") or field not in field_map:
            answer_callback(cq_id, "Трекро аз нав барои таҳрир интихоб кунед.", True)
            return
        code = state["data"]["code"]
        token = uuid.uuid4().hex[:12]
        set_state(admin_id, "adm_edit_track_value", {"field": field_map[field], "code": code, "token": token})
        answer_callback(cq_id)
        if field == "status":
            send_message(chat_id, f"📍 Мақоми {code}-ро интихоб кунед ё мақоми дигарро бо матн нависед:",
                         kb.admin_track_status_kb(token))
        else:
            send_message(chat_id, f"✏️ Қимати нави '{field}' барои {code}-ро нависед:")
        return

    if data.startswith("delok_") or data.startswith("delno_"):
        try:
            delivery_id = int(data.split("_", 1)[1])
        except ValueError:
            answer_callback(cq_id, "Дархост нодуруст аст.")
            return
        d = db.get_delivery(delivery_id)
        if not d:
            answer_callback(cq_id, "Дархост ёфт нашуд.")
            return
        status = "confirmed" if data.startswith("delok_") else "rejected"
        if not db.set_delivery_status(delivery_id, status, expected_status="pending_review"):
            answer_callback(cq_id, "Ин дархост аллакай баррасӣ шудааст.", True)
            return
        target_lang = lang_of(d["user_id"])
        if data.startswith("delok_"):
            send_message(d["user_id"], t("delivery_confirmed", target_lang))
            answer_callback(cq_id, "Тасдиқ шуд ✅")
        else:
            send_message(d["user_id"], t("delivery_rejected", target_lang, admin=admin_contact(target_lang)))
            answer_callback(cq_id, "Рад шуд ❌")
        return

    answer_callback(cq_id)


def handle_admin_text_state(message, admin_id, state):
    chat_id = message["chat"]["id"]
    text = message.get("text", "")
    action = state["action"]
    data = state["data"]

    if handle_accounting_text(message, admin_id, state):
        return

    if action == "adm_add_track_input":
        handle_admin_add_tracks(chat_id, admin_id, text)

    elif action == "adm_edit_track_select":
        code = text.strip().upper()
        track = db.get_track(code)
        if not track:
            send_message(chat_id, "❌ Ин трек-код ёфт нашуд.")
            clear_state(admin_id)
        else:
            set_state(admin_id, "adm_edit_track_fields", {"code": code})
            send_message(chat_id, f"Трек: {code}\nКадом майдонро таҳрир мекунед?", kb.admin_edit_track_field_kb(code))

    elif action == "adm_edit_track_fields":
        send_message(chat_id, "Майдонро бо тугма интихоб кунед ё /cancel нависед.", kb.admin_edit_track_field_kb(data["code"]))

    elif action == "adm_edit_track_value":
        try:
            db.update_track_field(data["code"], data["field"], text)
        except ValueError as error:
            send_message(chat_id, f"❌ {error}")
            return
        send_message(chat_id, "✅ Нав карда шуд.")
        clear_state(admin_id)

    elif action == "adm_del_track_input":
        code = text.strip().upper()
        archived = db.delete_track(code)
        send_message(chat_id, f"🗃 Трек {code} ба бойгонӣ гузошта шуд. Таърих дар омор мемонад." if archived else "❌ Ин трек-код ёфт нашуд.")
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
    data = callback.get("data", "")
    cq_id = callback["id"]
    chat = callback.get("message", {}).get("chat", {})
    chat_id = chat.get("id")
    if chat_id != user_id or chat.get("type", "private") != "private":
        answer_callback(cq_id, "Ботро дар чати хусусӣ истифода баред.", True)
        return

    if data.startswith("lang_"):
        lang = data.split("_", 1)[1]
        if lang not in ("tj", "ru", "en"):
            answer_callback(cq_id)
            return
        clear_state(user_id)
        db.set_language(user_id, lang)
        answer_callback(cq_id)
        send_message(chat_id, t("language_set", lang))
        show_main_menu(chat_id, user_id)
        return

    if data.startswith("paid_"):
        try:
            delivery_id = int(data.split("_", 1)[1])
        except ValueError:
            answer_callback(cq_id, "Дархост ёфт нашуд.", True)
            return
        d = db.get_delivery(delivery_id)
        if not d or d["user_id"] != user_id:
            answer_callback(cq_id, "Ин дархост ба шумо тааллуқ надорад.", True)
            return
        if d["status"] not in ("waiting_payment", "rejected"):
            answer_callback(cq_id, "Ин дархост аллакай фиристода ё тасдиқ шудааст.", True)
            return
        if not db.set_delivery_status(delivery_id, "pending_review", expected_status=d["status"]):
            answer_callback(cq_id, "Дархост аллакай нав шудааст.")
            return
        lang = lang_of(user_id)
        answer_callback(cq_id)
        send_message(chat_id, t("delivery_waiting_confirm", lang))
        u = db.get_user(user_id)
        admin_text = (f"🚚 Дархости доставка #{delivery_id}\n"
                       f"Трек: {d['track_code']}\nНом: {d['name']}\nТел: {d['phone']}\n"
                       f"Адрес: {d['address']}\nКорбар: {u['full_name'] if u else user_id}\n\n"
                       f"Пардохт ба {db.get_setting('payment_number', config.PAYMENT_NUMBER)} гуфта шудааст. Санҷед.")
        notify_admins(admin_text, kb.admin_delivery_review_kb(delivery_id))
        return

    if data.startswith(("adm_", "etf_", "ets_", "delok_", "delno_")):
        if is_admin(user_id):
            handle_admin_callback(callback, user_id)
        else:
            answer_callback(cq_id, "Ин имконият танҳо барои админ аст.", True)
        return

    answer_callback(cq_id)


# ============ Message dispatcher ============

def handle_message(message):
    if "from" not in message:
        return
    user_id = message["from"]["id"]
    chat_id = message["chat"]["id"]
    if chat_id != user_id or message["chat"].get("type", "private") != "private":
        return
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

    if text in ("/admin", "⚙️ Admin Panel") and is_admin(user_id):
        clear_state(user_id)
        open_admin_panel(chat_id)
        return

    if text in ("/stats", "/debtors", "/customers") and is_admin(user_id):
        clear_state(user_id)
        if text == "/stats":
            show_statistics(chat_id)
        elif text == "/debtors":
            show_debtors(chat_id)
        else:
            show_customers(chat_id)
        return

    if text in ("/cancel", t("btn_cancel", lang_of(user_id))):
        clear_state(user_id)
        show_main_menu(chat_id, user_id, "cancel")
        return

    state = get_state(user_id)
    if is_admin(user_id) and state and state["action"].startswith("adm_"):
        handle_admin_text_state(message, user_id, state)
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
    if text in (t("btn_instagram", lang), "/instagram"):
        clear_state(user_id)
        show_instagram(chat_id, lang)
        return
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
    if not config.BOT_TOKEN:
        raise SystemExit("BOT_TOKEN танзим нашудааст. Онро дар Variables гузоред.")
    print(f"{config.BOT_NAME} BOT — старт...")
    db.init_db()
    # Update the Telegram display name too; the @username stays unchanged.
    result = api("setMyName", {"name": config.BOT_NAME})
    if not result.get("ok"):
        print("[WARNING] setMyName failed; set the display name through @BotFather.")
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
