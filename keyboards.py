# -*- coding: utf-8 -*-
from texts import t


def main_menu_reply(lang, is_admin=False):
    kb = [
        [t("btn_search_track", lang), t("btn_my_tracks", lang)],
        [t("btn_forbidden", lang), t("btn_calc", lang)],
        [t("btn_warehouse", lang), t("btn_delivery", lang)],
        [t("btn_contact_admin", lang), t("btn_language", lang)],
        [t("btn_instagram", lang)],
    ]
    if is_admin:
        kb.append(["⚙️ Admin Panel"])
    return {"keyboard": kb, "resize_keyboard": True}


def contact_request_kb(lang):
    return {
        "keyboard": [[{"text": t("btn_share_contact", lang), "request_contact": True}]],
        "resize_keyboard": True,
        "one_time_keyboard": True,
    }


def language_inline_kb():
    return {
        "inline_keyboard": [
            [{"text": "🇹🇯 Тоҷикӣ", "callback_data": "lang_tj"}],
            [{"text": "🇷🇺 Русский", "callback_data": "lang_ru"}],
            [{"text": "🇬🇧 English", "callback_data": "lang_en"}],
        ]
    }


def cancel_reply_kb(lang):
    return {"keyboard": [[t("btn_cancel", lang)]], "resize_keyboard": True, "one_time_keyboard": True}


def paid_button_kb(lang, delivery_id):
    return {
        "inline_keyboard": [
            [{"text": t("btn_paid", lang), "callback_data": f"paid_{delivery_id}"}]
        ]
    }


def admin_delivery_review_kb(delivery_id):
    return {
        "inline_keyboard": [
            [
                {"text": "✅ Тасдиқ", "callback_data": f"delok_{delivery_id}"},
                {"text": "❌ Рад", "callback_data": f"delno_{delivery_id}"},
            ]
        ]
    }


def admin_panel_kb():
    return {
        "inline_keyboard": [
            [{"text": "➕ Илова кардани трек(ҳо)", "callback_data": "adm_add_track"}],
            [{"text": "✏️ Таҳрири трек", "callback_data": "adm_edit_track"},
             {"text": "🗃 Бойгонии трек", "callback_data": "adm_del_track"}],
            [{"text": "📋 Рӯйхати охирин трекҳо", "callback_data": "adm_list_tracks"}],
            [{"text": "📦 Борҳо расиданд", "callback_data": "adm_arrivals"},
             {"text": "✅ Додани бор", "callback_data": "adm_collect"}],
            [{"text": "📊 Омор", "callback_data": "adm_stats"}],
            [{"text": "💳 Ҳисоби муштариён", "callback_data": "adm_customers"},
             {"text": "📋 Қарздорон", "callback_data": "adm_debtors"}],
            [{"text": "👥 Корбарон", "callback_data": "adm_users"}],
            [{"text": "📷 Пайванди Instagram", "callback_data": "adm_edit_instagram"}],
            [{"text": "📢 Паём ба ҳама", "callback_data": "adm_broadcast"}],
            [{"text": "⛔ Таҳрири борҳои манъшуда", "callback_data": "adm_edit_forbidden"}],
            [{"text": "🏭 Таҳрири адреси склад", "callback_data": "adm_edit_warehouse"}],
            [{"text": "💰 Таҳрири нарх", "callback_data": "adm_edit_price"}],
            [{"text": "🚚 Дархостҳои доставкаи боқимонда", "callback_data": "adm_pending_deliveries"}],
        ]
    }


def admin_edit_track_field_kb(code):
    return {
        "inline_keyboard": [
            [{"text": "Ном", "callback_data": "etf_name"},
             {"text": "Мақом", "callback_data": "etf_status"}],
            [{"text": "Рӯзи расидан", "callback_data": "etf_days"},
             {"text": "Шаҳр", "callback_data": "etf_city"}],
        ]
    }


def back_to_admin_kb():
    return {"inline_keyboard": [[{"text": "⬅️ Бозгашт", "callback_data": "adm_panel"}]]}


def instagram_inline_kb(lang, url):
    return {"inline_keyboard": [[{"text": t("btn_open_instagram", lang), "url": url}]]}


def admin_track_status_kb(token):
    return {"inline_keyboard": [
        [{"text": "🇨🇳 Дар анбори Чин", "callback_data": f"ets_warehouse_{token}"},
         {"text": "🚚 Дар роҳ", "callback_data": f"ets_on_way_{token}"}],
        [{"text": "📦 Бор расид", "callback_data": f"ets_arrived_{token}"},
         {"text": "✅ Додан ба муштарӣ", "callback_data": f"ets_collected_{token}"}],
        [{"text": "⬅️ Панели админ", "callback_data": "adm_panel"}],
    ]}


def _page_buttons(prefix, page, pages):
    row = []
    if page > 0:
        row.append({"text": "⬅️ Пешина", "callback_data": f"{prefix}_{page - 1}"})
    if page + 1 < pages:
        row.append({"text": "Баъдӣ ➡️", "callback_data": f"{prefix}_{page + 1}"})
    return [row] if row else []


def customer_list_kb(customers, page, pages):
    rows = [[{"text": f"#{c['id']} · {c['full_name'][:35]}",
              "callback_data": f"adm_customer_{c['id']}"}] for c in customers]
    rows += _page_buttons("adm_customers", page, pages)
    rows += [
        [{"text": "➕ Муштарии нав", "callback_data": "adm_new_customer"}],
        [{"text": "📋 Қарздорон", "callback_data": "adm_debtors"},
         {"text": "⬅️ Панели админ", "callback_data": "adm_panel"}],
    ]
    return {"inline_keyboard": rows}


def customer_account_kb(customer_id):
    return {"inline_keyboard": [
        [{"text": "➕ Сабти қарз", "callback_data": f"adm_charge_{customer_id}"},
         {"text": "💵 Сабти пардохт", "callback_data": f"adm_payment_{customer_id}"}],
        [{"text": "📜 Таърихи ҳисоб", "callback_data": f"adm_history_{customer_id}"}],
        [{"text": "⬅️ Муштариён", "callback_data": "adm_customers"},
         {"text": "📋 Қарздорон", "callback_data": "adm_debtors"}],
    ]}


def ledger_confirm_kb(token):
    return {"inline_keyboard": [[
        {"text": "✅ Тасдиқи сабт", "callback_data": f"adm_ledger_confirm_{token}"},
        {"text": "❌ Бекор", "callback_data": f"adm_ledger_cancel_{token}"},
    ]]}


def debtors_kb(customers, page, pages):
    rows = [[{"text": f"#{c['id']} · {c['full_name'][:35]}",
              "callback_data": f"adm_customer_{c['id']}"}] for c in customers]
    rows += _page_buttons("adm_debtors", page, pages)
    rows += [
        [{"text": "📎 Рӯйхати пурра (CSV)", "callback_data": "adm_export_debtors"}],
        [{"text": "🔄 Навсозӣ", "callback_data": "adm_debtors"},
         {"text": "⬅️ Панели админ", "callback_data": "adm_panel"}],
    ]
    return {"inline_keyboard": rows}


def collection_customer_kb(customers, page, pages, token):
    rows = [[{"text": f"#{c['id']} · {c['full_name'][:30]} · {c['phone']}",
              "callback_data": f"adm_recipient_{c['id']}_{token}"}] for c in customers]
    page_row = []
    if page > 0:
        page_row.append({"text": "⬅️ Пешина", "callback_data": f"adm_recipients_{page - 1}_{token}"})
    if page + 1 < pages:
        page_row.append({"text": "Баъдӣ ➡️", "callback_data": f"adm_recipients_{page + 1}_{token}"})
    if page_row:
        rows.append(page_row)
    rows += [
        [{"text": "➕ Муштарии нав", "callback_data": f"adm_collect_new_{token}"}],
        [{"text": "❌ Бекор", "callback_data": f"adm_collect_cancel_{token}"}],
    ]
    return {"inline_keyboard": rows}


def collection_confirm_kb(token):
    return {"inline_keyboard": [[
        {"text": "✅ Бор дода шуд", "callback_data": f"adm_collect_confirm_{token}"},
        {"text": "❌ Бекор", "callback_data": f"adm_collect_cancel_{token}"},
    ]]}
