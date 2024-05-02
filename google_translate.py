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
    options.add_argument('--headless')
    options.add_argument('--disable-gpu')
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36")
    browser = webdriver.Chrome(options=options)
    logger.info('Начал загружать страницу переводчика гугл')
    browser.get(f"https://translate.google.com/?sl=auto&tl={lang_code}&text={input_text}&op=translate")
    page_state = browser.execute_script('return document.readyState;')
    logger.info('Страница загружена')
    i = 1
    while True:
        try:
            main_translation = str(browser.find_element(By.XPATH,
'//*[@id="yDmH0d"]/c-wiz/div/div[2]/c-wiz/div[2]/c-wiz/div[1]/div[2]/div[2]/c-wiz[2]/div[1]/div[6]/div/div[1]/*').text).strip()
            break
        except Exception as e:
            i += 1
            if i > 100:
                logger.error('Не прогрузилась страница гугл')
                raise ('Не прогрузилась страница гугл')
            sleep(0.5)
    i = 1
    t_list = []  #
    while True:
        try:
            browser.implicitly_wait(1)
            translated_text = (browser.find_element(By.XPATH,
                                           f'//*[@id="yDmH0d"]/c-wiz/div/div[2]/c-wiz/div[2]/c-wiz/div[1]/div[2]/div[2]/c-wiz[2]/div[2]/ol/div[{i}]/div[1]/div/div[1]')
                       .text)
            # //*[@id="yDmH0d"]/c-wiz/div/div[2]/c-wiz/div[2]/c-wiz/div[1]/div[2]/div[2]/c-wiz[2]/div[2]/ol/div[1]/div[1]/div/div[1]
            t = translated_text.split('\n')[0]
            t_list.append(t)
            i += 1
        except Exception as err:
            break

    phonetic = ''
    try:
        phonetic_text = (browser.find_element(By.XPATH,
                                       f'//*[@id="yDmH0d"]/c-wiz/div/div[2]/c-wiz/div[2]/c-wiz/div[1]/div[2]/div[3]/c-wiz[1]/div[2]//*').text)
        phonetic = phonetic_text.split('\n')[0]
    except:
        pass

    # формирование ответа
    syn_answer = ', '.join(t_list) if len(t_list) > 0 else ""

    return main_translation, syn_answer, phonetic


if __name__ == '__main__':
    translation, synonims_translation, phonetic = translate('home')
    print(translation, synonims_translation, phonetic)
