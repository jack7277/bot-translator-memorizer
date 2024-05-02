"""
Модели и методы работы с БД через SQLAlchemy.
"""
from datetime import datetime
from loguru import logger
from sqlalchemy import (Column, Integer, String, DateTime, create_engine, Boolean)
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker


# декларирование БД
base = declarative_base()
metadata = base.metadata
engine = create_engine('sqlite:///bot_db.sqlite')
Session = sessionmaker(bind=engine)
session = Session()


class DatabaseMixinModel:
    """Модель с общими методами для моделей базы данных"""
    @staticmethod
    def init_db():
        engine.connect()
        base.metadata.create_all(engine)
        pass
        # engine.connect()
        # base.metadata.create_all(engine)

    def connect_to_database(self):
        """соеднинение с БД"""
        pass

    def close_database_connection(self):
        """закрыть соединение с БД"""
        pass

    @staticmethod
    def db_add(element):  # noqa
        """
       Создание и добавление элемента в БД
        :param element:
        :return: True/False. true- успешное создание элемента в БД. False- неудачное создание
        """
        session.add(element)
        try:
            session.commit()
            result = True
        except SQLAlchemyError as e:  # возможно, ошибка должна быть другая
            logger.error(f'Ошибка при сохранении {element}, время: {datetime.now()}. Error: {e}')
            result = False
            session.rollback()
        return result


class Task(base, DatabaseMixinModel):
    """
    """
    __tablename__ = 'data_table'
    # __table_args__ = {
    #     'schema': 'data_schema'
    # }

    def __init__(self, **kwargs):
        self.chat_id = kwargs['chat_id']
        self.clean_text_to_translate = kwargs['clean_text_to_translate']
        self.phonetic = kwargs['phonetic']
        self.translation = kwargs['translation']
        self.synonims_translation = kwargs['synonims_translation']
        self.path_to_synth_voice = kwargs['path_to_synth_voice']

    uid = Column(Integer, primary_key=True, nullable=False, autoincrement=True)
    chat_id = Column(String())
    clean_text_to_translate = Column(String())
    phonetic = Column(String())
    translation = Column(String())
    synonims_translation = Column(String)
    path_to_synth_voice = Column(String())

    def __repr__(self):
        return f'Class _repr_'

    def __str__(self):
        return f'Class _str_'
