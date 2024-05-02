from time import sleep
from loguru import logger
import chromedriver_autoinstaller
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options


def translate(text):
    chromedriver_autoinstaller.install()

    # text = "Hello"
    LANGUAGE_CODE = 'ru'

    lang_code = 'ru'

    input_text = str(text).lower()

    options = Options()
    # options.add_argument('--headless')
    options.add_argument('--disable-gpu')
    # options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36")
    browser = webdriver.Chrome(options=options)
    logger.info('Начал загружать страницу переводчика гугл')
    browser.get(f"https://www.deepl.com/translator#en/ru/{text.replace(' ', '%20')}")
    page_state = browser.execute_script('return document.readyState;')
    logger.info('Страница загружена')

    main_translation = ''
    try:
        main_translation = str(browser.find_element(By.XPATH, "//*[@aria-labelledby='translation-target-heading'][@role='textbox']").text)
    except Exception as e:
        print(e)
    print(main_translation)


if __name__ == "__main__":
    translate('ravage lands')
