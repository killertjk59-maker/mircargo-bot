# -*- coding: utf-8 -*-
from texts import t


def main_menu_reply(lang, is_admin=False):
    kb = [
        [t("btn_search_track", lang), t("btn_my_tracks", lang)],
        [t("btn_forbidden", lang), t("btn_calc", lang)],
        [t("btn_warehouse", lang), t("btn_delivery", lang)],
        [t("btn_contact_admin", lang), t("btn_language", lang)],
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
             {"text": "🗑 Нест кардани трек", "callback_data": "adm_del_track"}],
            [{"text": "📋 Рӯйхати охирин трекҳо", "callback_data": "adm_list_tracks"}],
            [{"text": "👥 Корбарон", "callback_data": "adm_users"}],
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
            [{"text": "Ном", "callback_data": f"etf_name_{code}"},
             {"text": "Мақом", "callback_data": f"etf_status_{code}"}],
            [{"text": "Рӯзи расидан", "callback_data": f"etf_days_{code}"},
             {"text": "Шаҳр", "callback_data": f"etf_city_{code}"}],
        ]
    }


def back_to_admin_kb():
    return {"inline_keyboard": [[{"text": "⬅️ Бозгашт", "callback_data": "adm_panel"}]]}
