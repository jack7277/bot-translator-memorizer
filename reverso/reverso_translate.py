import os

from dotenv import load_dotenv
from reverso_context_api import Client

load_dotenv()
EMAIL = os.environ.get("EMAIL")
EMAIL_PWD = os.environ.get("EMAIL_PWD")
# направление перевода жестко EN -> RU
client = Client("en", "ru", credentials=(EMAIL, EMAIL_PWD))


async def get_reverso_translation(cttt):  # clean text to translate
    """
    получение перевода с сайта reverso
    """
    reverso_translation = list(client.get_translations(cttt))
    translation = ", ".join(reverso_translation)
    return translation


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

