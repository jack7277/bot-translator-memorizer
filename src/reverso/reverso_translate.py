"""
Перевод EN->RU через JSON-эндпоинт Reverso Context, без браузера/селениума.
Эндпоинт тот же, что дёргает сам сайт context.reverso.net, поэтому переводы,
транскрипция и примеры идентичны сайту, но без загрузки страницы и трекеров —
ответ приходит за ~0.3 с вместо ~15 с у селениума.
"""
import json
import re

import requests

# направление перевода жёстко EN -> RU
_URL = "https://context.reverso.net/bst-query-service"
_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"),
    "Content-Type": "application/json; charset=UTF-8",
    # Reverso требует Origin/Referer, иначе отдаёт не-JSON
    "Origin": "https://context.reverso.net",
    "Referer": "https://context.reverso.net/",
    "Connection": "close",
}
MAX_TRANSLATIONS = 5  # сколько вариантов перевода брать
MAX_EXAMPLES = 3      # сколько примеров брать


def _strip_tags(text):
    """Убирает HTML-теги вида <em>...</em>, которыми Reverso помечает совпадение."""
    return re.sub(r"<.*?>", "", text or "")


def translate_reverso(word, from_lang='en', to_lang='ru', retries=2):
    """
    Перевод слова/фразы через JSON-эндпоинт Reverso.
    @param word: слово или фраза для перевода
    @return: кортеж (перевод, транскрипция, определение, примеры использования)
    """
    payload = {
        "source_lang": from_lang,
        "target_lang": to_lang,
        "source_text": word,
        "target_text": "",
        "mode": 0,
        "npage": 1,
    }

    last_err = None
    data = None
    for _ in range(retries + 1):
        try:
            r = requests.post(_URL, headers=_HEADERS, data=json.dumps(payload), timeout=15)
            r.raise_for_status()
            data = r.json()
            break
        except Exception as e:  # разовые сетевые таймауты — ретраим
            last_err = e
    if data is None:
        raise RuntimeError(f"Reverso request failed: {last_err}")

    # переводы: первые N вариантов, как на сайте
    terms = [t for t in (e.get("term", "") for e in data.get("dictionary_entry_list", [])) if t]
    translation = "; ".join(terms[:MAX_TRANSLATIONS])

    # транскрипция (для EN обычно IPA)
    transliterations = data.get("sourceTransliterations") or []
    transliteration = transliterations[0].get("transliteration", "") if transliterations else ""

    # определение (для пары EN->RU Reverso обычно не отдаёт)
    definition = ""
    src_def = data.get("sourceDefinition")
    if isinstance(src_def, dict):
        definition = _strip_tags(src_def.get("text", ""))
    elif isinstance(src_def, str):
        definition = _strip_tags(src_def)

    # примеры: исходник + перевод, без подсветки
    examples = []
    for ex in data.get("list", [])[:MAX_EXAMPLES]:
        s = _strip_tags(ex.get("s_text", "")).strip()
        t = _strip_tags(ex.get("t_text", "")).strip()
        if s and t:
            examples.append(f"{s} — {t}")
    using_examples = "\n\n".join(examples)

    return translation, transliteration, definition, using_examples
