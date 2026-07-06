# -*- coding: utf-8 -*-
"""Ҷадвали даврии кӯҳна (short-form, 8 гурӯҳ, ба тарзи Менделеев)."""

ELEMENTS = [
    {"num": 1, "symbol": "H", "name": "Гидроген", "mass": 1.008, "period": 1, "group": "IA"},
    {"num": 2, "symbol": "He", "name": "Гелий", "mass": 4.003, "period": 1, "group": "VIIIA"},
    {"num": 3, "symbol": "Li", "name": "Литий", "mass": 6.94, "period": 2, "group": "IA"},
    {"num": 4, "symbol": "Be", "name": "Берилий", "mass": 9.012, "period": 2, "group": "IIA"},
    {"num": 5, "symbol": "B", "name": "Бор", "mass": 10.81, "period": 2, "group": "IIIA"},
    {"num": 6, "symbol": "C", "name": "Карбон", "mass": 12.01, "period": 2, "group": "IVA"},
    {"num": 7, "symbol": "N", "name": "Нитроген", "mass": 14.01, "period": 2, "group": "VA"},
    {"num": 8, "symbol": "O", "name": "Оксиген", "mass": 16.00, "period": 2, "group": "VIA"},
    {"num": 9, "symbol": "F", "name": "Флюор", "mass": 19.00, "period": 2, "group": "VIIA"},
    {"num": 10, "symbol": "Ne", "name": "Неон", "mass": 20.18, "period": 2, "group": "VIIIA"},
    {"num": 11, "symbol": "Na", "name": "Натрий", "mass": 22.99, "period": 3, "group": "IA"},
    {"num": 12, "symbol": "Mg", "name": "Магний", "mass": 24.31, "period": 3, "group": "IIA"},
    {"num": 13, "symbol": "Al", "name": "Алюминий", "mass": 26.98, "period": 3, "group": "IIIA"},
    {"num": 14, "symbol": "Si", "name": "Силитсий", "mass": 28.09, "period": 3, "group": "IVA"},
    {"num": 15, "symbol": "P", "name": "Фосфор", "mass": 30.97, "period": 3, "group": "VA"},
    {"num": 16, "symbol": "S", "name": "Сулфур", "mass": 32.07, "period": 3, "group": "VIA"},
    {"num": 17, "symbol": "Cl", "name": "Хлор", "mass": 35.45, "period": 3, "group": "VIIA"},
    {"num": 18, "symbol": "Ar", "name": "Аргон", "mass": 39.95, "period": 3, "group": "VIIIA"},
    {"num": 19, "symbol": "K", "name": "Калий", "mass": 39.10, "period": 4, "group": "IA"},
    {"num": 20, "symbol": "Ca", "name": "Калсий", "mass": 40.08, "period": 4, "group": "IIA"},
    {"num": 21, "symbol": "Sc", "name": "Скандий", "mass": 44.96, "period": 4, "group": "IIIB"},
    {"num": 22, "symbol": "Ti", "name": "Титан", "mass": 47.87, "period": 4, "group": "IVB"},
    {"num": 23, "symbol": "V", "name": "Ванадий", "mass": 50.94, "period": 4, "group": "VB"},
    {"num": 24, "symbol": "Cr", "name": "Хром", "mass": 52.00, "period": 4, "group": "VIB"},
    {"num": 25, "symbol": "Mn", "name": "Марганец", "mass": 54.94, "period": 4, "group": "VIIB"},
    {"num": 26, "symbol": "Fe", "name": "Оҳан", "mass": 55.85, "period": 4, "group": "VIIIB"},
    {"num": 27, "symbol": "Co", "name": "Кобалт", "mass": 58.93, "period": 4, "group": "VIIIB"},
    {"num": 28, "symbol": "Ni", "name": "Никел", "mass": 58.69, "period": 4, "group": "VIIIB"},
    {"num": 29, "symbol": "Cu", "name": "Мис", "mass": 63.55, "period": 4, "group": "IB"},
    {"num": 30, "symbol": "Zn", "name": "Руҳ", "mass": 65.38, "period": 4, "group": "IIB"},
    {"num": 31, "symbol": "Ga", "name": "Галлий", "mass": 69.72, "period": 4, "group": "IIIA"},
    {"num": 32, "symbol": "Ge", "name": "Германий", "mass": 72.63, "period": 4, "group": "IVA"},
    {"num": 33, "symbol": "As", "name": "Арсен", "mass": 74.92, "period": 4, "group": "VA"},
    {"num": 34, "symbol": "Se", "name": "Селен", "mass": 78.97, "period": 4, "group": "VIA"},
    {"num": 35, "symbol": "Br", "name": "Бром", "mass": 79.90, "period": 4, "group": "VIIA"},
    {"num": 36, "symbol": "Kr", "name": "Криптон", "mass": 83.80, "period": 4, "group": "VIIIA"},
    {"num": 37, "symbol": "Rb", "name": "Рубидий", "mass": 85.47, "period": 5, "group": "IA"},
    {"num": 38, "symbol": "Sr", "name": "Стронсий", "mass": 87.62, "period": 5, "group": "IIA"},
    {"num": 39, "symbol": "Y", "name": "Иттрий", "mass": 88.91, "period": 5, "group": "IIIB"},
    {"num": 40, "symbol": "Zr", "name": "Зирконий", "mass": 91.22, "period": 5, "group": "IVB"},
    {"num": 41, "symbol": "Nb", "name": "Ниобий", "mass": 92.91, "period": 5, "group": "VB"},
    {"num": 42, "symbol": "Mo", "name": "Молибден", "mass": 95.95, "period": 5, "group": "VIB"},
    {"num": 43, "symbol": "Tc", "name": "Технетсий", "mass": 98.0, "period": 5, "group": "VIIB"},
    {"num": 44, "symbol": "Ru", "name": "Рутений", "mass": 101.07, "period": 5, "group": "VIIIB"},
    {"num": 45, "symbol": "Rh", "name": "Родий", "mass": 102.91, "period": 5, "group": "VIIIB"},
    {"num": 46, "symbol": "Pd", "name": "Палладий", "mass": 106.42, "period": 5, "group": "VIIIB"},
    {"num": 47, "symbol": "Ag", "name": "Кумуш", "mass": 107.87, "period": 5, "group": "IB"},
    {"num": 48, "symbol": "Cd", "name": "Кадмий", "mass": 112.41, "period": 5, "group": "IIB"},
    {"num": 49, "symbol": "In", "name": "Индий", "mass": 114.82, "period": 5, "group": "IIIA"},
    {"num": 50, "symbol": "Sn", "name": "Қалъагӣ", "mass": 118.71, "period": 5, "group": "IVA"},
    {"num": 51, "symbol": "Sb", "name": "Сурма", "mass": 121.76, "period": 5, "group": "VA"},
    {"num": 52, "symbol": "Te", "name": "Теллур", "mass": 127.60, "period": 5, "group": "VIA"},
    {"num": 53, "symbol": "I", "name": "Йод", "mass": 126.90, "period": 5, "group": "VIIA"},
    {"num": 54, "symbol": "Xe", "name": "Ксенон", "mass": 131.29, "period": 5, "group": "VIIIA"},
    {"num": 55, "symbol": "Cs", "name": "Сезий", "mass": 132.91, "period": 6, "group": "IA"},
    {"num": 56, "symbol": "Ba", "name": "Барий", "mass": 137.33, "period": 6, "group": "IIA"},
    {"num": 72, "symbol": "Hf", "name": "Гафний", "mass": 178.49, "period": 6, "group": "IVB"},
    {"num": 73, "symbol": "Ta", "name": "Тантал", "mass": 180.95, "period": 6, "group": "VB"},
    {"num": 74, "symbol": "W", "name": "Волфрам", "mass": 183.84, "period": 6, "group": "VIB"},
    {"num": 75, "symbol": "Re", "name": "Рений", "mass": 186.21, "period": 6, "group": "VIIB"},
    {"num": 76, "symbol": "Os", "name": "Осмий", "mass": 190.23, "period": 6, "group": "VIIIB"},
    {"num": 77, "symbol": "Ir", "name": "Иридий", "mass": 192.22, "period": 6, "group": "VIIIB"},
    {"num": 78, "symbol": "Pt", "name": "Платина", "mass": 195.08, "period": 6, "group": "VIIIB"},
    {"num": 79, "symbol": "Au", "name": "Тилло", "mass": 196.97, "period": 6, "group": "IB"},
    {"num": 80, "symbol": "Hg", "name": "Симоб", "mass": 200.59, "period": 6, "group": "IIB"},
    {"num": 81, "symbol": "Tl", "name": "Таллий", "mass": 204.38, "period": 6, "group": "IIIA"},
    {"num": 82, "symbol": "Pb", "name": "Сурб", "mass": 207.2, "period": 6, "group": "IVA"},
    {"num": 83, "symbol": "Bi", "name": "Бисмут", "mass": 208.98, "period": 6, "group": "VA"},
    {"num": 84, "symbol": "Po", "name": "Полоний", "mass": 209.0, "period": 6, "group": "VIA"},
    {"num": 85, "symbol": "At", "name": "Астат", "mass": 210.0, "period": 6, "group": "VIIA"},
    {"num": 86, "symbol": "Rn", "name": "Радон", "mass": 222.0, "period": 6, "group": "VIIIA"},
    {"num": 87, "symbol": "Fr", "name": "Франсий", "mass": 223.0, "period": 7, "group": "IA"},
    {"num": 88, "symbol": "Ra", "name": "Радий", "mass": 226.0, "period": 7, "group": "IIA"},
    {"num": 92, "symbol": "U", "name": "Уран", "mass": 238.03, "period": 7, "group": "IIIB"},
]

GROUPS = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII"]

ELEMENTS_BY_NUM = {e["num"]: e for e in ELEMENTS}
MASS_BY_SYMBOL = {e["symbol"]: e["mass"] for e in ELEMENTS}


def elements_in_group(roman):
    result = [e for e in ELEMENTS if e["group"] in (roman + "A", roman + "B")]
    result.sort(key=lambda e: (e["period"], e["group"]))
    return result


def get_element(num):
    return ELEMENTS_BY_NUM.get(int(num))


def get_mass(symbol):
    return MASS_BY_SYMBOL.get(symbol)
