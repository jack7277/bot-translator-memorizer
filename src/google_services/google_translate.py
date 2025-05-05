from json import loads

import requests


async def google_transle(cttt):
    """
    получение перевода с сайта google translate
    """
    """
    Here are some values for dt. If the value is set, the following data will be returned:
    t - translation of source text
    at - alternate translations
    rm - transcription / transliteration of source and translated texts
    bd - dictionary, in case source text is one word (you get translations with articles, reverse translations, etc.)
    md - definitions of source text, if it's one word
    ss - synonyms of source text, if it's one word
    ex - examples
    rw - See also list.
    dj - Json response with names. (dj=1)
    """
    text_to_translate = "consider"
    client1 = 't?client=dict-chrome-ex'
    c1_url = 'https://clients5.google.com'
    client2 = 'single?client=gtx'
    c2_url = 'https://translate.googleapis.com'
    dictionary = '&dt=bd'
    definition_of_source = '&dt=md'
    examples = '&dt=ex'
    source_lang = '&sl=en'  # english
    destination_lang = '&tl=ru'  # russian
    alternate_translations = '&dt=at'
    transcription = '&dt=rm'
    json_response = '&dj=1'
    model = '&model=nmt'
    url = (f"{c2_url}/translate_a/{client2}"
           f"{source_lang}"
           f"{destination_lang}"
           f"{alternate_translations}"
           f"{examples}"
           f"{transcription}"
           f"{definition_of_source}"
           f"{dictionary}"
           f"{json_response}"
           f"{model}"
           f"&q={cttt}")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Content-Type": "application/json",  # если POST-запрос
    }

    session = requests.Session()
    response = session.get(url, headers=headers)  # или .post()
    # print(response.status_code)
    translated_text = loads(response.text)
    # print(translated_text)
    phonetic = translated_text['sentences'][0]['src_translit']
    print('Транслитерация: ' + phonetic)
    translation = ", ".join(translated_text['dict'][0]['terms'])
    print('Перевод: ' + translation)
    definition = translated_text['definitions'][0]['entry'][0]['gloss']
    print(f"Определение: {definition}")

    examples_list = translated_text['examples']['example']
    using_examples = ''
    for example in examples_list:
        text = example['text']
        print(f"Пример: {text}")
        using_examples += text + '\n\n'

    # translation, phonetic, using_examples
    return translation, phonetic, definition, using_examples
