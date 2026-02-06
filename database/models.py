"""
Модели базы данных (SQLAlchemy)
"""
from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean, JSON
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()


class User(Base):
    """Модель пользователя"""
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True, nullable=False, index=True)
    username = Column(String(255))
    first_name = Column(String(255))
    language = Column(String(10), default='ru')
    persona = Column(String(50), default='assistant')
    model = Column(String(100), default='auto')
    image_model = Column(String(100), default='auto')
    age = Column(Integer, nullable=True)  # пример: добавлено через миграцию 002
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Message(Base):
    """Модель сообщения в истории диалога"""
    __tablename__ = 'messages'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False, index=True)
    role = Column(String(20), nullable=False)  # 'user' или 'assistant'
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class Stats(Base):
    """Модель статистики пользователя"""
    __tablename__ = 'stats'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, unique=True, nullable=False, index=True)
    requests_count = Column(Integer, default=0)
    tokens_used = Column(Integer, default=0)
    images_generated = Column(Integer, default=0)
    commands_used = Column(JSON, default=dict)  # {"start": 5, "help": 2}
    start_date = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Favorite(Base):
    """Модель избранного"""
    __tablename__ = 'favorites'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False, index=True)
    content = Column(Text, nullable=False)
    content_type = Column(String(50), default='text')  # 'text' или 'image'
    tags = Column(JSON, default=list)
    created_at = Column(DateTime, default=datetime.utcnow)


class Subscription(Base):
    """Подписка пользователя (Telegram Stars)"""
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, unique=True, nullable=False, index=True)
    tier = Column(String(20), default="free")  # free, premium
    stars_paid_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class UsageDaily(Base):
    """Дневной счётчик запросов (для лимита бесплатного тарифа)"""
    __tablename__ = "usage_daily"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False, index=True)
    date = Column(String(10), nullable=False, index=True)  # YYYY-MM-DD
    count = Column(Integer, default=0)
    __table_args__ = ({"sqlite_autoincrement": True},)


class UserFact(Base):
    """Факты о пользователе (RAG Lite — долгосрочная память)"""
    __tablename__ = "user_facts"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False, index=True)
    fact_type = Column(String(50), nullable=False)  # name, age, job, city
    fact_value = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class Achievement(Base):
    """Модель достижений пользователя"""
    __tablename__ = 'achievements'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False, index=True)
    achievement_id = Column(String(100), nullable=False)
    unlocked_at = Column(DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        {'sqlite_autoincrement': True},
    )
