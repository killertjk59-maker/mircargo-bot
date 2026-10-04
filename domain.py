"""Validation and exact-money helpers shared by the bot and database."""
import re
from decimal import Decimal
from urllib.parse import urlsplit, urlunsplit


CARGO_STATUS_KEYS = {
    "warehouse": "status_warehouse",
    "on_way": "status_on_way",
    "arrived": "status_arrived",
    "collected": "status_collected",
}


def normalize_track_code(value):
    code = value.strip().upper()
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9_.\-/]{0,39}", code):
        raise ValueError("Трек бояд аз 1–40 ҳарфу рақами лотинӣ бошад (инчунин - _ . /).")
    return code


def normalize_phone(value):
    phone = re.sub(r"[\s()\-]", "", value.strip())
    if phone.startswith("00"):
        phone = "+" + phone[2:]
    if phone.startswith("+"):
        phone = phone[1:]
    if not re.fullmatch(r"[0-9]{7,15}", phone):
        raise ValueError("Рақами телефонро дуруст нависед, масалан: +992901234567.")
    # Local Tajik numbers and international +992 numbers identify the same person.
    if len(phone) == 9:
        phone = "992" + phone
    return "+" + phone


def parse_money(value):
    """Return positive TJS as integer dirams, never as a binary float."""
    value = value.strip().replace(",", ".")
    if not re.fullmatch(r"[0-9]{1,9}(?:\.[0-9]{1,2})?", value):
        raise ValueError("Маблағи мусбат нависед, то 2 рақам пас аз нуқта (масалан: 125.50).")
    amount = int(Decimal(value) * 100)
    if amount <= 0:
        raise ValueError("Маблағ бояд аз сифр зиёд бошад.")
    return amount


def format_money(amount):
    sign = "-" if amount < 0 else ""
    amount = abs(amount)
    return f"{sign}{amount // 100}.{amount % 100:02d}"


def normalize_instagram_url(value):
    value = value.strip()
    if value.startswith("@"):
        username = value[1:]
        if not re.fullmatch(r"[A-Za-z0-9_.]{1,30}", username):
            raise ValueError("Юзернейми Instagram нодуруст аст.")
        value = f"https://www.instagram.com/{username}/"
    try:
        parts = urlsplit(value)
        valid = (
            len(value) <= 512
            and not any(char.isspace() or ord(char) < 32 for char in value)
            and parts.scheme == "https"
            and parts.hostname in {"instagram.com", "www.instagram.com", "m.instagram.com"}
            and parts.port is None
            and parts.username is None
            and parts.password is None
            and "\\" not in value
        )
    except ValueError:
        valid = False
    if not valid:
        raise ValueError("Пайванди https://www.instagram.com/… ё @username-ро нависед.")
    return urlunsplit(("https", parts.hostname, parts.path or "/", parts.query, ""))


def lifecycle_from_status(status):
    """Recognize existing standard statuses without guessing from track searches."""
    value = status.strip().casefold()
    # Legacy admins often prefixed a status with an emoji or check mark.
    while value and not value[0].isalnum():
        value = value[1:].lstrip()
    aliases = {
        "warehouse": ("warehouse", "дар анбор", "дар анбори", "на складе", "at china warehouse"),
        "on_way": ("on_way", "дар роҳ", "в пути", "on the way"),
        "arrived": ("arrived", "parcel arrived", "расид", "расидааст", "бор расид", "бор омад", "омадааст", "прибыл", "поступил"),
        "collected": ("collected", "гирифта шуд", "гирифта шудааст", "бор гирифта шуд", "ба муштарӣ дода шуд", "получен", "получено", "выдан", "выдано", "delivered"),
    }
    for lifecycle, prefixes in aliases.items():
        if any(value == prefix or value.startswith(prefix + " ") for prefix in prefixes):
            return lifecycle
    return "custom"
