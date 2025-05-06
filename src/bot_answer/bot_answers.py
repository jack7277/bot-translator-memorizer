MAX_SYNONYMS = 7


async def full_answer(clean_text_to_translate, phonetic, translation, definition='', using_examples=''):
    """
    Подготовка полного текста ответа бота
    Слово - транскрипция, перевод, примеры
    """
    if definition != '':
        add_definition = f'Определение: {definition}\n\n'
    else:
        add_definition = ''

    bot_answer_to_user = (f'{clean_text_to_translate}       {phonetic}\n'
                          f'{str(translation)}\n\n'
                          f'{add_definition}'
                          f'Примеры: {using_examples}')
    return bot_answer_to_user


async def short_answer(clean_text_to_translate, phonetic, translation, using_examples: str):
    """
    Короткий ответ бота для повторов, максимум 7 синонимов
    """
    bot_answer_to_user = f'{clean_text_to_translate}       {phonetic}\n\n'
    bot_answer_to_user += f'{str(translation)}\n'
    try:
        tmp = str(using_examples).split(',')
        bot_answer_to_user += f'\n'
        l = []

        max = len(tmp) if len(tmp) < MAX_SYNONYMS else MAX_SYNONYMS
        for i in range(0, max):
            bot_answer_to_user += f'{tmp[i]}'
            if (i + 1) != max:
                bot_answer_to_user += ', '
    except:
        pass

    return bot_answer_to_user
