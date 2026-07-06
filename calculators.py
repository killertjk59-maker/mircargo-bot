# -*- coding: utf-8 -*-
"""Ҳисобкунаки массаи молярӣ — таҳлили формулаи химиявӣ."""
from elements_data import get_mass


class FormulaError(Exception):
    pass


def parse_formula(formula):
    formula = formula.strip().replace(" ", "")
    if not formula:
        raise FormulaError("Формула холӣ аст.")

    pos = 0

    def read_number():
        nonlocal pos
        start = pos
        while pos < len(formula) and formula[pos].isdigit():
            pos += 1
        return int(formula[start:pos]) if pos > start else 1

    def parse_level():
        nonlocal pos
        counts = {}
        while pos < len(formula) and formula[pos] != ')':
            ch = formula[pos]
            if ch == '(':
                pos += 1
                sub = parse_level()
                if pos >= len(formula) or formula[pos] != ')':
                    raise FormulaError("Қавс баста нашудааст: '('")
                pos += 1
                num = read_number()
                for el, cnt in sub.items():
                    counts[el] = counts.get(el, 0) + cnt * num
            elif ch.isupper():
                start = pos
                pos += 1
                while pos < len(formula) and formula[pos].islower():
                    pos += 1
                el = formula[start:pos]
                num = read_number()
                counts[el] = counts.get(el, 0) + num
            else:
                raise FormulaError(f"Аломати нодуруст: '{ch}'")
        return counts

    result = parse_level()
    if pos != len(formula):
        raise FormulaError("Қавс кушода мондааст ё формула нодуруст аст.")
    if not result:
        raise FormulaError("Ягон унсур пайдо нашуд.")
    return result


def molar_mass(formula):
    counts = parse_formula(formula)
    total = 0.0
    lines = []
    for symbol, count in counts.items():
        mass = get_mass(symbol)
        if mass is None:
            raise FormulaError(f"Унсури '{symbol}' дар пойгоҳи додаҳо нест.")
        subtotal = mass * count
        total += subtotal
        lines.append(f"{symbol}: {mass} × {count} = {subtotal:.3f}")
    breakdown = "\n".join(lines)
    return total, breakdown
