import os

from dotenv import load_dotenv
from reverso_context_api import Client

load_dotenv()
EMAIL = os.environ.get("EMAIL")
EMAIL_PWD = os.environ.get("EMAIL_PWD")
# направление перевода жестко EN -> RU
client = Client("en", "ru", credentials=(EMAIL, EMAIL_PWD))


# @deprecated("Больше не работает")
async def get_reverso_translation(cttt):  # clean text to translate
    """
    получение перевода с сайта reverso
    """
    reverso_translation = list(client.get_translations(cttt))
    translation = ", ".join(reverso_translation)
    return translation


# @deprecated("Больше не работает")
async def get_reverso_synonims(cttt):
    """
    Получение синонимов слова с сайта реверсо
    """
    synonims_translation = '\n'
    samples = client.get_translation_samples(cttt, cleanup=True)
    try:
        for i, context in enumerate(samples):
            if i == 0: continue
            synonims_translation += context[0] + '\n\n'
            if i > 3:
                break
    except:
        pass
    return synonims_translation


import re

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


async def translate_reverso_selenium(word, from_lang='en', to_lang='ru'):
    MAX_NUM = 4

    url = f'https://context.reverso.net/перевод/английский-русский/{word}'

    options = Options()
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36")
    options.add_argument("--headless")  # Работает в фоне

    driver = webdriver.Chrome(options=options)
    driver.get(url)
    driver.implicitly_wait(1)

    # Явное ожидание появления блока с переводом
    wait = WebDriverWait(driver, 10)  # Ждем до 10 секунд
    context_box = wait.until(
        EC.presence_of_element_located((By.CLASS_NAME, 'example'))
    )

    try:
        # беру транслит если есть
        transliteration = driver.find_element(By.ID, 'transliteration-content')
        transliteration_text = transliteration.text
    except:
        transliteration_text = ''

    translation_text = ''
    # элементы с переводом
    translations = (driver
                    .find_elements(By.XPATH,
                                   "//*[@id='translations-content']/*[contains(@class, 'translation')]"))
    for i, translation in enumerate(translations):
        if i > MAX_NUM: break
        translation_text += translation.text + "; "
    translation_text = re.sub(r'[; ]+$', '', translation_text)  # Удаляет запятые и пробелы в конце

    isNullOrWhiteSpace = lambda s: not s or s.isspace()

    # если тру, то ничего не нашел в прошлый раз
    if isNullOrWhiteSpace(translation_text):
        # Ищем элемент с переводом
        # translation = driver.find_element(By.ID, 'top-results')
        translation = driver.find_element(By.XPATH, "//*[contains(@class, 'trg  ltr')]//*[@class='text']")
        translation_text = translation.text

    # Примеры
    examples = driver.find_elements(By.CLASS_NAME, 'example')
    using_examples = ''
    for i, example in enumerate(examples):
        if i > MAX_NUM: break
        using_examples += example.text + '\n\n'

    # translation, transliteration, definition, using_examples
    driver.quit()
    return translation_text, transliteration_text, '', using_examples
