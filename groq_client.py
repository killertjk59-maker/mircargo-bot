# -*- coding: utf-8 -*-
"""Муштарии оддии Groq API (танҳо requests, бе SDK) — мутобиқ бо Termux."""
import os
import time
import requests

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = "llama-3.3-70b-versatile"

SYSTEM_PROMPT_TEACHER = (
    "Ту як муаллими химия ҳастӣ, ки бо забони тоҷикӣ ба хонандагони мактабу литсей "
    "мавзӯъҳои химияро содда, дақиқ ва бо мисолҳои амалӣ мефаҳмонӣ. "
    "Ҳамеша ҷавобҳоро кӯтоҳ, сохторёфта ва бо истилоҳоти химиявии дуруст деҳ. "
    "Агар формула ё ҳисобкунӣ лозим шавад, қадам ба қадам нишон деҳ."
)

SYSTEM_PROMPT_EXAMPLE = (
    "Ту муаллими химия ҳастӣ. Барои категорияи додашуда ЯК масъалаи нави омӯзишӣ "
    "(на мисоли қаблӣ) бо забони тоҷикӣ тартиб деҳ ва фавран ҳалли пурраи қадам ба "
    "қадами онро низ нависон. Ҷавобро кӯтоҳ ва фаҳмо нигоҳ дор."
)


def _call_groq(messages, max_tokens=600, retries=3):
    if not GROQ_API_KEY:
        return "⚠️ GROQ_API_KEY танзим нашудааст. Лутфан дар .env илова кунед."

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": MODEL,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0.6,
    }

    for attempt in range(retries):
        try:
            resp = requests.post(GROQ_URL, headers=headers, json=payload, timeout=30)
            if resp.status_code == 429:
                time.sleep(2 ** attempt)
                continue
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()
        except requests.exceptions.RequestException as e:
            if attempt == retries - 1:
                return f"⚠️ Хатои пайваст бо AI: {e}"
            time.sleep(1.5 * (attempt + 1))
    return "⚠️ AI ҳозир ҷавоб дода натавонист. Дубора кӯшиш кунед."


def ask_teacher(question):
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT_TEACHER},
        {"role": "user", "content": question},
    ]
    return _call_groq(messages, max_tokens=700)


def generate_example(category_title):
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT_EXAMPLE},
        {"role": "user", "content": f"Мавзӯъ: {category_title}"},
    ]
    return _call_groq(messages, max_tokens=600)
