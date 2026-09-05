import asyncio
import base64
import logging
import os
import random
import re
import socket
import sys
from datetime import datetime, timedelta
from time import sleep

import requests
from aiogram import Bot, Dispatcher, types
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiohttp.resolver import AbstractResolver
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import Message, BufferedInputFile, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.markdown import hbold
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv
from loguru import logger

from src.bot_answer import bot_answers
from src.db import models
from src.google_services.text_to_speech import tts
from src.reverso import reverso_translate

scheduler = AsyncIOScheduler()
dp = Dispatcher()

load_dotenv()
BOT_TOKEN = os.environ.get("TOKEN")
PROXY_PAGE_URL = "https://mtpro.xyz/socks5-ru"
# Доступный (незаблокированный) IP Bot API. DNS отдаёт заблокированный адрес,
# поэтому резолвим сами. Сертификат и SNI остаются на домен, проверяются как обычно.
TELEGRAM_API_IP = "149.154.167.220"


class StaticApiResolver(AbstractResolver):
    """Резолвит заданные хосты в фиксированные IP в обход DNS."""

    def __init__(self, mapping: dict[str, str]) -> None:
        self._mapping = mapping

    async def resolve(self, host, port=0, family=socket.AF_INET):
        return [{
            "hostname": host,
            "host": self._mapping.get(host, host),
            "port": port,
            "family": family,
            "proto": 0,
            "flags": 0,
        }]

    async def close(self):
        pass


def get_proxy_url() -> str | None:
    try:
        page = requests.get(PROXY_PAGE_URL, timeout=10)
        page.raise_for_status()
        script_urls = re.findall(r'<script[^>]+src=["\']([^"\']+)["\']', page.text)
        script_url = next(url for url in script_urls if "autoptimize" in url)
        script_url = requests.compat.urljoin(PROXY_PAGE_URL, script_url)

        script = requests.get(script_url, timeout=10)
        script.raise_for_status()
        encoded = re.search(r"eval\(atob\('([^']+)'\)\)", script.text).group(1)
        decoded = base64.b64decode(encoded).decode("utf-8")
        proxies = re.findall(r'"ip":"([^" ]+)","port":(\d+)', decoded)
        proxy_ip, proxy_port = random.choice(proxies)
        return f"socks5://{proxy_ip}:{proxy_port}"
    except (requests.RequestException, AttributeError, IndexError,
            StopIteration, TypeError, ValueError) as err:
        logger.warning(f"Could not load proxy list: {err}")
        return None


def create_bot() -> Bot:
    # MTProto-прокси (например, 127.0.0.1:1443 от TgWsProxy) не подходит:
    # aiogram обращается к Bot API по обычному HTTPS, а не по MTProto.
    # PROXY из окружения (http://... или socks5://...) — опционально.
    proxy = os.environ.get("PROXY")
    if proxy:
        session = AiohttpSession(proxy=proxy)
    else:
        session = AiohttpSession()
        # DNS отдаёт заблокированный IP — подменяем резолвер на статический
        session._connector_init["resolver"] = StaticApiResolver(
            {"api.telegram.org": TELEGRAM_API_IP})
    logger.info(f"Telegram API IP: {TELEGRAM_API_IP}, proxy: {proxy or 'none'}")
    return Bot(BOT_TOKEN, session=session,
               default=DefaultBotProperties(parse_mode=ParseMode.HTML))


bot = create_bot()

# Constants
MAX_PHRASE_LENGTH = 200


async def reminder(remind_message: str):
    """
    Вызов планировщиком напоминания, сообщение для повторения
    @param remind_message: Содержит "user_id;сообщение"
    """
    user_id = remind_message.split(";")[0]
    clean_text = remind_message.split(";")[-1]

    db_record = await models.db_request(clean_text)

    if len(db_record) > 0:
        obj = db_record[-1]
        with open(obj.path_to_synth_voice, mode="rb") as f:
            ff = f.read()

        link_to_file = BufferedInputFile(file=ff, filename=obj.path_to_synth_voice)

        bot_answer_to_user = await (bot_answers.short_answer
                                    (clean_text_to_translate=obj.clean_text_to_translate,
                                     phonetic=obj.phonetic,
                                     translation=obj.translation,
                                     using_examples=obj.synonims_translation))

        button = InlineKeyboardButton(text="Удолить", callback_data="button_delete")
        keyboard_inline = InlineKeyboardMarkup(inline_keyboard=[[button]], row_width=1)

        try:
            # если боту запрещено слать голосовые сообщения юзеру, то тут можно упасть
            await bot.send_voice(chat_id=user_id, voice=link_to_file, caption=bot_answer_to_user,
                                 reply_markup=keyboard_inline)
        except:
            pass


@dp.message(CommandStart())
async def command_start_handler(message: Message) -> None:
    """
    # команда /start боту, он кидает приветственное сообщение
    """
    await message.answer(f"Привет, {hbold(message.from_user.full_name)}!\n"
                         f"Напиши мне слово или фразу на английском и я сделаю перевод.\n"
                         f"Потом по кривой забывания буду слать напоминания.\n"
                         f"Необходимо разрешить боту слать вам голосовые сообщения.")


async def user_input_processing(message: types.Message):
    """
    Обработка сообщения от пользователя,
    @param message: Сообщение юзера типа Message
    @return:
    """

    try:
        logger.info(f'\n'
                    f'User FullName: {message.from_user.full_name}\n'
                    f'User ID: {message.from_user.id}\n'
                    f'User Text: {message.text}')

        # чищу введенный текст
        clean_text_to_translate = message.text.strip().lower().replace('\n', ' ')

        # Длинные фразу фтопку
        if len(clean_text_to_translate) > MAX_PHRASE_LENGTH:
            await bot.send_message(chat_id=message.from_user.id,
                                   text='чота больно длинная фраза, не хочу ничего делать сорян')
            return

        # ищу в бд такое слово/фразу
        db_records = await models.db_request(clean_text_to_translate.replace("/f", "").strip())

        # если в бд уже есть такое слово и юзер не передал ключ /f, то возвращаю последнюю запись из бд, какбэ кэш
        if len(db_records) > 0 and not clean_text_to_translate.endswith('/f'):
            db_records = db_records[-1]  # из базы беру последнюю запись

            # открываю файл mp3 для этой фразы/слова
            with open(db_records.path_to_synth_voice, mode="rb") as f:
                pronounce_mp3_file = f.read()

            # ссылка до мп3 файла
            link_to_file = BufferedInputFile(file=pronounce_mp3_file, filename=db_records.path_to_synth_voice)

            bot_answer_to_user = await (bot_answers.full_answer
                                        (clean_text_to_translate=db_records.clean_text_to_translate,
                                         phonetic=db_records.phonetic,
                                         translation=db_records.translation,
                                         using_examples=db_records.synonims_translation))

            logger.info(f"\n"
                        f"Bot Full Answer:\n"
                        f"{bot_answer_to_user}")

            await message.delete()  # удаляю запрос юзера
            bot_message = await bot.send_voice(chat_id=message.chat.id,
                                               voice=link_to_file,
                                               caption=bot_answer_to_user,
                                               reply_markup=keyboard_inline)
            return

        # слова нет в бд или передан со словом ключ /f (force), то обновляю перевод и заношу в базу
        clean_text_to_translate = clean_text_to_translate.replace('/f', '').strip()

        wait_message = await bot.send_message(chat_id=message.from_user.id, text='ждите...')

        # генерирую mp3 движком гугла text to speech
        clean_path_synth_voice = tts('en', clean_text_to_translate)

        # Работает с гуглом, но иногда возвращает мусор
        # translation, phonetic, definition, using_examples = await (google_translate
        #                                                            .google_transle(clean_text_to_translate))

        # reverso через selenium
        translation, phonetic, definition, using_examples = await (reverso_translate
                                                                   .translate_reverso_selenium(clean_text_to_translate))

        # Этот способ через псевдо-апи больше не работает
        # reverso = reverso_translate.get_reverso_translation(clean_text_to_translate)
        # translation = await asyncio.wait_for(reverso, 5)
        # synonims = reverso_translate.get_reverso_synonims(clean_text_to_translate)
        # synonims_translation = await asyncio.wait_for(synonims, 5)
        # phonetic = ''

        with open(clean_path_synth_voice, mode="rb") as f:
            pronounce_mp3_file = f.read()
        f = BufferedInputFile(file=pronounce_mp3_file, filename=clean_path_synth_voice)

        bot_answer_to_user = await bot_answers.full_answer(
            clean_text_to_translate=clean_text_to_translate,
            phonetic=phonetic,
            translation=translation,
            definition=definition,
            using_examples=using_examples)

        logger.info(f"{bot_answer_to_user}")
        bot_message = await bot.send_voice(chat_id=message.chat.id,
                                           voice=f,
                                           caption=bot_answer_to_user,
                                           reply_markup=keyboard_inline)  # отвечаю на запрос переводом

        user_id = message.from_user.id
        chat_id = message.chat.id

        # удаляю все старые записи
        await models.delete_old_records(db_records)

        task_to_save = models.Task(chat_id=chat_id,
                                   clean_text_to_translate=clean_text_to_translate,
                                   phonetic=phonetic,
                                   translation=translation,
                                   synonims_translation=using_examples,
                                   path_to_synth_voice=clean_path_synth_voice)
        is_ok = models.DatabaseMixinModel.db_add(task_to_save)

        await message.delete()  # удаляю запрос юзера
        await bot.delete_message(chat_id=wait_message.chat.id, message_id=wait_message.message_id)  # удаляю фразу ждите

    except Exception as err:
        logger.warning(str(err))


@dp.message()
async def echo_handler(message: types.Message) -> None:
    """
    Обработка запроса слова от пользователя
    By default, message handler will handle all message types (like a text, photo, sticker etc.)
    """
    task1 = asyncio.Task(user_input_processing(message))
    await task1


@dp.callback_query(lambda c: c.data == 'button_delete')
async def button_delete(callback_query: types.CallbackQuery):
    """
    Нажатие на кнопку Удолить, для удаления напоминания
    @param callback_query:
    """
    chat_id = callback_query.message.chat.id
    msg_id = callback_query.message.message_id
    await bot.delete_message(chat_id, msg_id)


@dp.callback_query(lambda c: c.data == 'button_remember')
async def button_remember(callback_query: types.CallbackQuery):
    """
    Нажатие на кнопку Сохранить для занесения слова в запоминание
    @param callback_query:
    """
    user_id = callback_query.from_user.id
    msg_id = callback_query.message.message_id
    chat_id = callback_query.message.chat.id
    clean_original_text = callback_query.message.caption
    await callback_query.answer()  # Отправляем подтверждение обработки callback запроса

    # r1 = datetime.now()  # .replace(hour=12, minute=0, second=0, microsecond=0)
    now_h = datetime.now().hour
    if now_h < 15:
        r1 = datetime.now().replace(hour=15, minute=0, second=0, microsecond=0)
    if now_h < 12:
        r1 = datetime.now().replace(hour=12, minute=0, second=0, microsecond=0)
    if now_h >= 15:
        r1 = (datetime.now() + timedelta(days=1)).replace(hour=11, minute=0, second=0, microsecond=0)

    r2 = r1 + timedelta(seconds=5)
    # r3 = r2 + timedelta(seconds=5)
    r3 = r1 + timedelta(minutes=60)
    r4 = r3 + timedelta(hours=5)
    r5 = r1 + timedelta(days=1)
    r6 = r5 + timedelta(days=1)
    r7 = r6 + timedelta(days=1)
    r8 = r7 + timedelta(days=5)
    r9 = r8 + timedelta(weeks=2)
    r10 = r9 + timedelta(weeks=4)
    r11 = r10 + timedelta(weeks=10)
    r12 = r11 + timedelta(weeks=16)

    reminder_list = [r1, r2]  # for tests
    reminder_list = [r3, r4, r5, r6, r7, r8, r9, r10, r11, r12]
    req_text = clean_original_text.split("       ")[0]
    req = f'{user_id};{req_text}'

    for rem_x in reminder_list:
        # noinspection PyTypeChecker
        job = scheduler.add_job(func=reminder, trigger='date', args=[req], misfire_grace_time=None,
                                run_date=rem_x)

    # msg_notify = await bot.send_message(
    #     text='Напоминалка будет через 30 минут, 1 день, 2 недели, 2.5 мес',
    #     chat_id=chat_id)

    # меняю текст клаиватуры
    button2 = InlineKeyboardButton(text="⇈СХРНЛ⇈", callback_data="button_remember")
    keyboard_inline = InlineKeyboardMarkup(inline_keyboard=[[button2]], row_width=1)
    try:
        # здесь первое изменение
        await bot.edit_message_reply_markup(chat_id=chat_id, message_id=msg_id, reply_markup=keyboard_inline)
    except:
        # повторное нажатие кнопки приводит к ошибке, что менять нечего, кнопка уже изменена на ГОТОВО
        pass

    # await asyncio.sleep(5)
    # await bot.delete_message(chat_id=chat_id, message_id=msg_notify.message_id)


async def main() -> None:
    scheduler.add_jobstore('sqlalchemy', url='sqlite:///jobs.sqlite')
    scheduler.start()
    await dp.start_polling(bot, polling_timeout=60)


if __name__ == "__main__":
    # на случай падения - рестарт бота
    while True:
        try:
            logger.add("logs\\log.log", rotation="100 MB")
            logger.info('Start')

            bot = create_bot()

            # базовая кнопка Запомнить на переводе, обработки - button_remember
            button2 = InlineKeyboardButton(text="⇈ЗАПОМНИ⇈", callback_data="button_remember")
            keyboard_inline = InlineKeyboardMarkup(inline_keyboard=[[button2]], row_width=1)
            # инит sqlalchemy модель
            dashboard_db = models.DatabaseMixinModel()
            dashboard_db.init_db()
            logging.basicConfig(level=logging.INFO, stream=sys.stdout)

            asyncio.run(main())

        except Exception as e:
            print(str(e))
            print('Restart in 5 sec')
            sleep(5)
