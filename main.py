"""
Телеграм-бот: перевод EN->RU + запоминание по кривой забывания.
Взаимодействие с телеграмом — чистый requests + getUpdates, без фреймворка.
"""
import html
import json
import logging
import os
import sys
from datetime import datetime, timedelta
from time import sleep

import requests
import urllib3
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv
from loguru import logger
from requests.adapters import HTTPAdapter

from src.bot_answer import bot_answers
from src.db import models
from src.google_services.text_to_speech import tts
from src.reverso import reverso_translate

load_dotenv()
BOT_TOKEN = os.environ.get("TOKEN")
API_BASE = f"https://api.telegram.org/bot{BOT_TOKEN}"

# Constants
MAX_PHRASE_LENGTH = 200

# Доступный (незаблокированный) IP Bot API. DNS отдаёт заблокированный адрес,
# поэтому подключаемся к IP, а SNI и проверка сертификата остаются на домене.
TELEGRAM_API_IP = "149.154.167.220"


class _PinnedHTTPSConnection(urllib3.connection.HTTPSConnection):
    """Соединяется с фиксированным IP, но Host и SNI остаются api.telegram.org."""

    def _new_conn(self):
        if self.host != "api.telegram.org":
            return super()._new_conn()
        from urllib3.util import connection as _urllib3_conn
        try:
            return _urllib3_conn.create_connection(
                (TELEGRAM_API_IP, self.port),
                self.timeout,
                source_address=self.source_address,
                socket_options=self.socket_options,
            )
        except OSError as e:
            raise urllib3.exceptions.NewConnectionError(
                self, f"Failed to establish a new connection: {e}") from e


class _PinnedHTTPSPool(urllib3.HTTPSConnectionPool):
    ConnectionCls = _PinnedHTTPSConnection


class _PinnedPoolManager(urllib3.PoolManager):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.pool_classes_by_scheme = {"http": urllib3.HTTPConnectionPool,
                                       "https": _PinnedHTTPSPool}


class _PinnedHTTPAdapter(HTTPAdapter):
    def init_poolmanager(self, connections, maxsize, block=False, **pool_kwargs):
        self.poolmanager = _PinnedPoolManager(
            num_pools=connections, maxsize=maxsize, block=block, **pool_kwargs)


_session = requests.Session()
_session.mount("https://", _PinnedHTTPAdapter())

# планировщик напоминаний, создается при старте в __main__
scheduler = None

REMEMBER_KEYBOARD = {"inline_keyboard": [[
    {"text": "⇈ЗАПОМНИ⇈", "callback_data": "button_remember"}]]}
SAVED_KEYBOARD = {"inline_keyboard": [[
    {"text": "⇈СХРНЛ⇈", "callback_data": "button_remember"}]]}
DELETE_KEYBOARD = {"inline_keyboard": [[
    {"text": "Удолить", "callback_data": "button_delete"}]]}


def tg(method: str, req_timeout: int = 30, **params):
    """
    Вызов метода Bot API.
    Для методов с файлами передавать открытый файловый объект (multipart).
    req_timeout — таймаут соединения; не путать с параметром timeout самого метода.
    """
    params = {k: (json.dumps(v) if isinstance(v, (dict, list)) else v)
              for k, v in params.items() if v is not None}
    if any(hasattr(v, "read") for v in params.values()):
        resp = _session.post(f"{API_BASE}/{method}", data=params,
                             timeout=req_timeout, allow_redirects=False)
    else:
        resp = _session.post(f"{API_BASE}/{method}", json=params,
                             timeout=req_timeout, allow_redirects=False)
    data = resp.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram API {method}: {data}")
    return data["result"]


def reminder(remind_message: str):
    """
    Вызов планировщиком напоминания, сообщение для повторения
    @param remind_message: Содержит "user_id;сообщение"
    """
    user_id = remind_message.split(";")[0]
    clean_text = remind_message.split(";")[-1]

    db_record = models.db_request(clean_text)

    if len(db_record) > 0:
        obj = db_record[-1]

        bot_answer_to_user = bot_answers.short_answer(
            clean_text_to_translate=obj.clean_text_to_translate,
            phonetic=obj.phonetic,
            translation=obj.translation,
            using_examples=obj.synonims_translation)

        try:
            # если боту запрещено слать голосовые сообщения юзеру, то тут можно упасть
            with open(obj.path_to_synth_voice, mode="rb") as f:
                tg("sendVoice", chat_id=user_id, voice=f,
                   caption=bot_answer_to_user, reply_markup=DELETE_KEYBOARD)
        except Exception:
            pass


def command_start_handler(chat_id: int, full_name: str) -> None:
    """
    команда /start боту, он кидает приветственное сообщение
    """
    tg("sendMessage", chat_id=chat_id,
       text=f"Привет, <b>{html.escape(full_name)}</b>!\n"
            f"Напиши мне слово или фразу на английском и я сделаю перевод.\n"
            f"Потом по кривой забывания буду слать напоминания.\n"
            f"Необходимо разрешить боту слать вам голосовые сообщения.",
       parse_mode="HTML")


def user_input_processing(message: dict):
    """
    Обработка сообщения от пользователя
    @param message: словарь Message из апдейта телеграма
    """
    try:
        user = message.get("from") or {}
        chat_id = message["chat"]["id"]
        user_id = user.get("id", chat_id)
        full_name = " ".join(p for p in (user.get("first_name"), user.get("last_name")) if p)

        logger.info(f'\n'
                    f'User FullName: {full_name}\n'
                    f'User ID: {user_id}\n'
                    f'User Text: {message.get("text")}')

        # чищу введенный текст
        clean_text_to_translate = (message.get("text") or "").strip().lower().replace('\n', ' ')

        # Длинные фразу фтопку
        if len(clean_text_to_translate) > MAX_PHRASE_LENGTH:
            tg("sendMessage", chat_id=user_id,
               text='чота больно длинная фраза, не хочу ничего делать сорян')
            return

        # ищу в бд такое слово/фразу
        db_records = models.db_request(clean_text_to_translate.replace("/f", "").strip())

        # если в бд уже есть такое слово и юзер не передал ключ /f, то возвращаю последнюю запись из бд, какбэ кэш
        if len(db_records) > 0 and not clean_text_to_translate.endswith('/f'):
            db_record = db_records[-1]  # из базы беру последнюю запись

            bot_answer_to_user = bot_answers.full_answer(
                clean_text_to_translate=db_record.clean_text_to_translate,
                phonetic=db_record.phonetic,
                translation=db_record.translation,
                using_examples=db_record.synonims_translation)

            logger.info(f"\n"
                        f"Bot Full Answer:\n"
                        f"{bot_answer_to_user}")

            tg("deleteMessage", chat_id=chat_id, message_id=message["message_id"])
            with open(db_record.path_to_synth_voice, mode="rb") as f:
                tg("sendVoice", chat_id=chat_id, voice=f,
                   caption=bot_answer_to_user, reply_markup=REMEMBER_KEYBOARD)
            return

        # слова нет в бд или передан со словом ключ /f (force), то обновляю перевод и заношу в базу
        clean_text_to_translate = clean_text_to_translate.replace('/f', '').strip()

        wait_message = tg("sendMessage", chat_id=user_id, text='ждите...')

        # генерирую mp3 движком гугла text to speech
        clean_path_synth_voice = tts('en', clean_text_to_translate)

        # reverso через JSON-эндпоинт (без селениума)
        translation, phonetic, definition, using_examples = (reverso_translate
                                                             .translate_reverso(clean_text_to_translate))

        bot_answer_to_user = bot_answers.full_answer(
            clean_text_to_translate=clean_text_to_translate,
            phonetic=phonetic,
            translation=translation,
            definition=definition,
            using_examples=using_examples)

        logger.info(f"{bot_answer_to_user}")

        with open(clean_path_synth_voice, mode="rb") as f:
            tg("sendVoice", chat_id=chat_id, voice=f,
               caption=bot_answer_to_user, reply_markup=REMEMBER_KEYBOARD)

        # удаляю все старые записи
        models.delete_old_records(db_records)

        task_to_save = models.Task(chat_id=chat_id,
                                   clean_text_to_translate=clean_text_to_translate,
                                   phonetic=phonetic,
                                   translation=translation,
                                   synonims_translation=using_examples,
                                   path_to_synth_voice=clean_path_synth_voice)
        models.DatabaseMixinModel.db_add(task_to_save)

        tg("deleteMessage", chat_id=chat_id, message_id=message["message_id"])  # удаляю запрос юзера
        tg("deleteMessage", chat_id=wait_message["chat"]["id"],
           message_id=wait_message["message_id"])  # удаляю фразу ждите

    except Exception as err:
        logger.warning(str(err))


def button_delete(callback_query: dict):
    """
    Нажатие на кнопку Удолить, для удаления напоминания
    """
    message = callback_query["message"]
    tg("deleteMessage", chat_id=message["chat"]["id"], message_id=message["message_id"])


def button_remember(callback_query: dict):
    """
    Нажатие на кнопку Сохранить для занесения слова в запоминание
    """
    message = callback_query["message"]
    user_id = callback_query["from"]["id"]
    msg_id = message["message_id"]
    chat_id = message["chat"]["id"]
    clean_original_text = message.get("caption") or ""
    tg("answerCallbackQuery", callback_query_id=callback_query["id"])

    now_h = datetime.now().hour
    if now_h < 15:
        r1 = datetime.now().replace(hour=15, minute=0, second=0, microsecond=0)
    if now_h < 12:
        r1 = datetime.now().replace(hour=12, minute=0, second=0, microsecond=0)
    if now_h >= 15:
        r1 = (datetime.now() + timedelta(days=1)).replace(hour=11, minute=0, second=0, microsecond=0)

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

    reminder_list = [r3, r4, r5, r6, r7, r8, r9, r10, r11, r12]
    req_text = clean_original_text.split("       ")[0]
    req = f'{user_id};{req_text}'

    for rem_x in reminder_list:
        scheduler.add_job(func=reminder, trigger='date', args=[req], misfire_grace_time=None,
                          run_date=rem_x)

    try:
        # здесь первое изменение
        tg("editMessageReplyMarkup", chat_id=chat_id, message_id=msg_id, reply_markup=SAVED_KEYBOARD)
    except Exception:
        # повторное нажатие кнопки приводит к ошибке, что менять нечего, кнопка уже изменена
        pass


def handle_update(update: dict):
    """
    Разбор апдейта из getUpdates: коллбеки и сообщения
    """
    if "callback_query" in update:
        callback_query = update["callback_query"]
        data = callback_query.get("data")
        if data == "button_delete":
            button_delete(callback_query)
        elif data == "button_remember":
            button_remember(callback_query)
        return

    message = update.get("message")
    if not message or not message.get("text"):
        return

    text = message["text"]
    command = text.split()[0].split("@")[0].lower()
    if command == "/start":
        user = message.get("from") or {}
        full_name = " ".join(p for p in (user.get("first_name"), user.get("last_name")) if p)
        command_start_handler(message["chat"]["id"], full_name)
        return

    user_input_processing(message)


def main() -> None:
    """
    Цикл long polling getUpdates
    """
    offset = None
    logger.info("Start polling")
    while True:
        params = {"timeout": 55, "allowed_updates": ["message", "callback_query"]}
        if offset is not None:
            params["offset"] = offset
        try:
            updates = tg("getUpdates", req_timeout=70, **params)
        except Exception as err:
            logger.warning(f"getUpdates: {err}")
            sleep(5)
            continue

        for update in updates:
            offset = update["update_id"] + 1
            try:
                handle_update(update)
            except Exception as err:
                logger.warning(str(err))


if __name__ == "__main__":
    # на случай падения - рестарт бота
    while True:
        try:
            logger.add("logs\\log.log", rotation="100 MB")
            logger.info('Start')

            # базовая кнопка Запомнить на переводе, обработки - button_remember

            # инит sqlalchemy модель
            dashboard_db = models.DatabaseMixinModel()
            dashboard_db.init_db()
            logging.basicConfig(level=logging.INFO, stream=sys.stdout)

            scheduler = BackgroundScheduler()
            scheduler.add_jobstore('sqlalchemy', url='sqlite:///jobs.sqlite')
            scheduler.start()

            main()

        except Exception as e:
            print(str(e))
            print('Restart in 5 sec')
            sleep(5)
