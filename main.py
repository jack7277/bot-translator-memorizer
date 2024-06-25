import os
from datetime import datetime, timedelta

from aiogram.client.default import DefaultBotProperties
from dotenv import load_dotenv
from loguru import logger
from gtts import gTTS
import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import Message, BufferedInputFile, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from aiogram.utils.markdown import hbold

from apscheduler.executors.pool import ProcessPoolExecutor
from apscheduler.schedulers.asyncio import AsyncIOScheduler

import models

from reverso_context_api import Client

executors = {
    'default': {'type': 'threadpool', 'max_workers': 200},
    'processpool': ProcessPoolExecutor(max_workers=50)
}
job_defaults = {
    'coalesce': False,
    'max_instances': 30
}

scheduler = AsyncIOScheduler()
words = []

load_dotenv()
TOKEN = os.environ.get("TOKEN")
EMAIL = os.environ.get("EMAIL")
EMAIL_PWD = os.environ.get("EMAIL_PWD")

client = Client("en", "ru", credentials=(EMAIL, EMAIL_PWD))

dp = Dispatcher()
bot = Bot(TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
logger.add("logs\log.log", rotation="100 MB")
logger.info('Start')

button2 = InlineKeyboardButton(text="⇈ЗАПОМНИ⇈", callback_data="button_remember")
keyboard_inline = InlineKeyboardMarkup(inline_keyboard=[[button2]], row_width=1)

dashboard_db = models.DatabaseMixinModel()
dashboard_db.init_db()


@dp.message(CommandStart())
async def command_start_handler(message: Message) -> None:
    """
    This handler receives messages with `/start` command
    """
    await message.answer(f"Привет, {hbold(message.from_user.full_name)}!\n"
                         f"Напиши мне слово или фразу на английском и я сделаю перевод. Необходимо разрешить боту слать вам голосовые сообщения.")


def tts(lang, clean_text_to_translate):
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
    tts.save(filename)
    # на выходе filename относительный путь до mp3
    return filename


async def prepare_bot_answer(clean_text_to_translate, phonetic, translation, syn_answer):
    bot_answer_to_user = f'{clean_text_to_translate}       {phonetic}\n'
    bot_answer_to_user += (f'{str(translation)}\n'
                           f'{syn_answer}')
    return bot_answer_to_user


async def prepare_short_bot_answer(clean_text_to_translate, phonetic, translation, syn_answer: str):
    bot_answer_to_user = f'{clean_text_to_translate}       {phonetic}\n'
    bot_answer_to_user += f'{str(translation)}'
    try:
        tmp = str(syn_answer).split(',')
        bot_answer_to_user += f'\n'
        l = []
        max = len(tmp) if len(tmp) < 7 else 7
        for i in range(0, max):
            bot_answer_to_user += f'{tmp[i]}'
            if (i + 1) != max:
                bot_answer_to_user += ', '
    except:
        pass
    return bot_answer_to_user


async def get_reverso_translation(cttt):  # clean text to translate
    reverso_translation = list(client.get_translations(cttt))
    translation = ", ".join(reverso_translation)
    return translation


async def get_reverso_synonims(cttt):
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


@dp.message()
async def echo_handler(message: types.Message) -> None:
    """
    Handler will forward receive a message back to the sender
    By default, message handler will handle all message types (like a text, photo, sticker etc.)
    """
    try:
        ikb = InlineKeyboardButton(text="Перейти", web_app=WebAppInfo(url="base.html"))
        # kb = KeyboardButton(text="Перейти", web_app=WebAppInfo(url="base.html"))
        # msg = await bot.send_message(chat_id=message.from_user.id, text='старт')

        logger.info(f'{message.from_user.full_name}, {message.from_user.id}: {message.text}')
        # ищу в бд такое слово/фразу
        clean_text_to_translate = message.text.strip().lower().replace('\n', ' ')
        if len(clean_text_to_translate) > 200:
            await bot.send_message(chat_id=message.from_user.id,
                                   text='чота больно длинная фраза, не хочу ничего делать сорян')
            return

        db_obj = (models.session
                  .query(models.Task)
                  .filter(models.Task.clean_text_to_translate == clean_text_to_translate)
                  .all())

        # в базе нашел такое слово/фразу
        if len(db_obj) > 0 and not clean_text_to_translate.endswith('/f'):
            # msg = await bot.send_message(chat_id=message.from_user.id, text='Такой запрос уже сохранен в базу...')
            obj = db_obj[-1]
            with open(obj.path_to_synth_voice, mode="rb") as f:
                ff = f.read()
            link_to_file = BufferedInputFile(file=ff, filename=obj.path_to_synth_voice)
            bot_answer_to_user = await prepare_bot_answer(obj.clean_text_to_translate, obj.phonetic, obj.translation,
                                                          obj.synonims_translation)
            logger.info(f"{bot_answer_to_user}")
            await message.delete()  # удаляю запрос юзера
            bot_message = await bot.send_voice(chat_id=message.chat.id,
                                               voice=link_to_file,
                                               caption=bot_answer_to_user,
                                               reply_markup=keyboard_inline)
            return

        clean_text_to_translate = clean_text_to_translate.replace('/f', '').strip()

        msg = await bot.send_message(chat_id=message.from_user.id, text='ждите...')
        clean_path_synth_voice = tts('en', clean_text_to_translate)
        # translation, synonims_translation, phonetic = google_translate.translate(clean_text_to_translate)

        translation = await get_reverso_translation(clean_text_to_translate)
        synonims_translation = await get_reverso_synonims(clean_text_to_translate)
        phonetic = ''

        with open(clean_path_synth_voice, mode="rb") as f:
            ff = f.read()
        f = BufferedInputFile(file=ff, filename=clean_path_synth_voice)
        bot_answer_to_user = await prepare_bot_answer(clean_text_to_translate, phonetic, translation,
                                                      synonims_translation)
        logger.info(f"{bot_answer_to_user}")
        bot_message = await bot.send_voice(chat_id=message.chat.id,
                                           voice=f,
                                           caption=bot_answer_to_user,
                                           reply_markup=keyboard_inline)  # отвечаю на запрос переводом

        user_id = message.from_user.id
        chat_id = message.chat.id

        task = models.Task(chat_id=chat_id, clean_text_to_translate=clean_text_to_translate,
                           phonetic=phonetic, translation=translation, synonims_translation=synonims_translation
                           , path_to_synth_voice=clean_path_synth_voice)
        models.DatabaseMixinModel.db_add(task)

        await message.delete()  # удаляю запрос юзера
        await bot.delete_message(chat_id=msg.chat.id, message_id=msg.message_id)  # удаляю фразу ждите

    except Exception as err:
        logger.warning(str(err))


async def reminder(msg: str):
    user_id = msg.split(";")[0]
    # msg_id = msg.split(";")[1]
    clean_original_text = msg.split(";")[-1]

    db_obj = (models.session
              .query(models.Task)
              .filter(models.Task.clean_text_to_translate == clean_original_text)
              .all())
    if len(db_obj) > 0:
        obj = db_obj[-1]
        with open(obj.path_to_synth_voice, mode="rb") as f:
            ff = f.read()
        link_to_file = BufferedInputFile(file=ff, filename=obj.path_to_synth_voice)

        bot_answer_to_user = await prepare_short_bot_answer(obj.clean_text_to_translate, obj.phonetic, obj.translation,
                                                            obj.synonims_translation)

        button = InlineKeyboardButton(text="Удолить", callback_data="button_delete")
        keyboard_inline = InlineKeyboardMarkup(inline_keyboard=[[button]], row_width=1)
        await bot.send_voice(chat_id=user_id, voice=link_to_file, caption=bot_answer_to_user,
                             reply_markup=keyboard_inline)


@dp.callback_query(lambda c: c.data == 'button_delete')
async def button(callback_query: types.CallbackQuery):
    chat_id = callback_query.message.chat.id
    msg_id = callback_query.message.message_id
    await bot.delete_message(chat_id, msg_id)


@dp.callback_query(lambda c: c.data == 'button_remember')
async def button(callback_query: types.CallbackQuery):
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

    reminder_list = [r1, r2]
    reminder_list = [r3, r4, r5, r6, r7, r8, r9, r10, r11, r12]
    req_text = clean_original_text.split("       ")[0]
    req = f'{user_id};{req_text}'

    for rem_x in reminder_list:
        job = scheduler.add_job(func=reminder, trigger='date', args=[req], misfire_grace_time=None,
                                run_date=rem_x)
        # print(str(job))

    # msg_notify = await bot.send_message(
    #     text='Напоминалка будет через 30 минут, 1 день, 2 недели, 2.5 мес',
    #     chat_id=chat_id)

    # меняю текст клаиватуры
    button2 = InlineKeyboardButton(text="⇈СХРНЛ⇈", callback_data="button_remember")
    keyboard_inline = InlineKeyboardMarkup(inline_keyboard=[[button2]], row_width=1)
    try:
        # здесь первое изменение
        await bot.edit_message_reply_markup(chat_id=chat_id, message_id=msg_id, reply_markup=keyboard_inline)
    except Exception as err:
        # повторное нажатие кнопки приводит к ошибке что менять нечего, кнопка уже изменена на ГОТОВО
        print(str(err))

    # await asyncio.sleep(5)
    # await bot.delete_message(chat_id=chat_id, message_id=msg_notify.message_id)


async def main() -> None:
    scheduler.add_jobstore('sqlalchemy', url='sqlite:///jobs.sqlite')
    scheduler.start()
    await dp.start_polling(bot, polling_timeout=600)


if __name__ == "__main__":
    while True:
        try:
            dashboard_db = models.DatabaseMixinModel()
            dashboard_db.init_db()

            logging.basicConfig(level=logging.INFO, stream=sys.stdout)
            asyncio.run(main())
        except:
            pass
