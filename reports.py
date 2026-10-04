"""Admin-only report formatting; all amounts are integer dirams."""
import csv
import datetime
import io

from domain import format_money


_LOCAL_TZ = datetime.timezone(datetime.timedelta(hours=5))  # Asia/Dushanbe


def local_datetime(value):
    if not value:
        return "—"
    date = datetime.datetime.fromisoformat(value)
    if date.tzinfo is None:
        date = date.replace(tzinfo=datetime.timezone.utc)
    return date.astimezone(_LOCAL_TZ).strftime("%d.%m.%Y %H:%M")


def statistics_text(stats):
    lines = [
        "📊 Tezcargo — омори умумӣ",
        "Ҳисоб аз ҳамаи сабтҳои нигоҳдошташуда.",
        "",
        "📦 Борҳо",
        f"• Ҳамагӣ трекҳо: {stats['tracks_total']}",
        f"• Фаъол: {stats['active_tracks']} | Бойгонӣ: {stats['archived_tracks']}",
        f"• Дар анбори Чин: {stats['warehouse']}",
        f"• Дар роҳ: {stats['on_way']}",
        f"• Ҳамагӣ расидаанд: {stats['arrived_total']}",
        f"• Расида, ҳоло интизори гирифтан: {stats['awaiting_collection']}",
        f"• Ба муштариён дода шудаанд: {stats['collected']}",
        f"• Муштариёни гуногуне, ки бор гирифтаанд: {stats['collectors']}",
        f"• Бо мақоми дигар: {stats['other_status']}",
        "",
        "👥 Корбарон ва муштариён",
        f"• Корбарони бот: {stats['users_total']}",
        f"• Сабти номшуда: {stats['registered_users']}",
        f"• Муштариён дар ҳисобдорӣ: {stats['customers_total']}",
        f"• Ҷустуҷӯҳои муваффақи трек: {stats['searches']}",
        f"• Корбарони ҷустуҷӯкарда: {stats['search_users']}",
        "",
        "💳 Ҳисоби муштариён (сомонӣ)",
        f"• Ҳамагӣ маблағи қарзҳои сабтшуда: {format_money(stats['total_charges'])}",
        f"• Ҳамагӣ пардохти сабтшуда: {format_money(stats['total_payments'])}",
        f"• Қарзи боқимонда: {format_money(stats['outstanding'])}",
        f"• Қарздорон: {stats['debtors_count']}",
        f"• Аванси муштариён: {format_money(stats['credit'])}",
        "",
        "🚚 Дархостҳои доставка",
        f"• Ҳамагӣ: {stats['deliveries_total']}",
        f"• Интизори пардохт: {stats['deliveries_waiting']}",
        f"• Интизори санҷиши админ: {stats['deliveries_pending']}",
        f"• Тасдиқшуда: {stats['deliveries_confirmed']}",
        f"• Радшуда: {stats['deliveries_rejected']}",
        "",
        "ℹ️ Тасдиқи пардохти доставка маънои гирифтани борро надорад.",
        "Қарз/пардохти ҳисобдорӣ аз тарафи админ алоҳида сабт мешавад.",
    ]
    if stats['unassigned_collected']:
        lines += [f"⚠️ {stats['unassigned_collected']} бори кӯҳна гирифта шудааст, вале муштарии он маълум нест. "
                  "Онҳо ба шумораи муштариёни гуногун дохил намешаванд."]
    return "\n".join(lines)


def customer_text(account):
    balance = account['balance']
    remaining = f"Қарзи боқимонда: {format_money(balance)}" if balance >= 0 else f"Аванс: {format_money(-balance)}"
    return (f"💳 Муштарии #{account['id']}\n"
            f"👤 {account['full_name']}\n📱 {account['phone']}\n\n"
            f"Маблағи қарзҳои сабтшуда: {format_money(account['total_charges'])} сомонӣ\n"
            f"Пардохти сабтшуда: {format_money(account['total_payments'])} сомонӣ\n"
            f"{remaining} сомонӣ\n"
            f"Охирин амалиёт: {local_datetime(account['last_entry_at'])}")


def customers_text(accounts, count, page, pages):
    lines = [f"💳 Ҳисоби муштариён — ҳамагӣ: {count}", f"Саҳифа {page + 1}/{pages}", ""]
    for account in accounts:
        balance = account['balance']
        label = "қарз" if balance >= 0 else "аванс"
        lines.append(f"#{account['id']} · {account['full_name']}\n"
                     f"{account['phone']} · {label}: {format_money(abs(balance))} сомонӣ")
    if not accounts:
        lines.append("Ҳоло муштарӣ нест. «Муштарии нав»-ро пахш кунед.")
    return "\n\n".join(lines)


def debtors_text(accounts, summary, page, pages):
    lines = ["📋 Tezcargo — рӯйхати қарздорон",
             f"Ҳамагӣ: {summary['debtors_count']} муштарӣ",
             f"Қарзи умумии боқимонда: {format_money(summary['outstanding'])} сомонӣ",
             f"Саҳифа {page + 1}/{pages}"]
    for account in accounts:
        lines.append(f"👤 #{account['id']} · {account['full_name']}\n"
                     f"📱 {account['phone']}\n"
                     f"Қарз: {format_money(account['total_charges'])} | "
                     f"Пардохт: {format_money(account['total_payments'])}\n"
                     f"🔴 Боқимонда: {format_money(account['balance'])} сомонӣ")
    if not accounts:
        lines.append("✅ Ҳоло қарздор нест.")
    else:
        lines.append("Рӯйхати пурраро бо тугмаи CSV зеркашӣ кунед.")
    return "\n\n".join(lines)


def history_text(account, entries):
    lines = [f"📜 10 амалиёти охирини {account['full_name']} (#{account['id']})"]
    for entry in entries:
        label = "Қарз" if entry['entry_type'] == 'charge' else "Пардохт"
        note = entry['note'][:120] + ("…" if len(entry['note']) > 120 else "")
        lines.append(f"#{entry['id']} · {label}: {format_money(entry['amount_minor'])} сомонӣ\n"
                     f"{local_datetime(entry['created_at'])} · админ: {entry['created_by']}\n{note or '—'}")
    if not entries:
        lines.append("Ҳоло амалиёт нест.")
    return "\n\n".join(lines)


def _csv_text(value):
    # Prevent user-entered names/phones from becoming spreadsheet formulas.
    value = str(value)
    if value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def debtors_csv(accounts):
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(["ID", "Ном", "Телефон", "Қарзҳои сабтшуда (TJS)",
                     "Пардохтҳо (TJS)", "Қарзи боқимонда (TJS)", "Охирин амалиёт (Душанбе)"])
    for account in accounts:
        writer.writerow([account['id'], _csv_text(account['full_name']), _csv_text(account['phone']),
                         format_money(account['total_charges']), format_money(account['total_payments']),
                         format_money(account['balance']), local_datetime(account['last_entry_at'])])
    # BOM makes Tajik/Cyrillic text readable in Excel without selecting encoding.
    return stream.getvalue().encode("utf-8-sig")
