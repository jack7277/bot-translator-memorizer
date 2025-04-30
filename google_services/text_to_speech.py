from gtts import gTTS


def tts(lang, clean_text_to_translate):
    """
    Функция текст в речь через синтезатор гугла, на входе
    lang - язык
    clean_text_to_translate - текст для озвучки
    filename - на выходе filename относительный путь до mp3
    """

    # удаление лишних символов
    def remove(value, deletechars):
        for c in deletechars:
            value = value.replace(c, '')
        return value

    # формируем mp3 с озвучкой
    # lang = 'en'  # Входной параметр язык оригинала
    text_to_translate = clean_text_to_translate.replace('\n', ' ').strip().lower()

    tts = gTTS(text=text_to_translate, lang=lang, slow=True)
    clean_filename = remove(text_to_translate, '\/:*?"<>|')
    filename = f"pronounce\{str(clean_filename)}.mp3"
    tts.save(filename)  # сохраняю мр3
    return filename

