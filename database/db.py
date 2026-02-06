"""
Работа с базой данных SQLite через aiosqlite
"""
import json
from typing import Optional, List, Dict, Any
from datetime import datetime
from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from .models import Base, User, Message, Stats, Favorite, Achievement
import logging

logger = logging.getLogger(__name__)

# Путь к базе данных
DB_PATH = 'bot_database.db'


class Database:
    """Класс для работы с базой данных"""
    
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self.engine = None
        self.async_session = None
    
    async def init(self):
        """Инициализация базы данных"""
        # Создаем асинхронный движок SQLite
        self.engine = create_async_engine(
            f'sqlite+aiosqlite:///{self.db_path}',
            echo=False
        )
        
        # Создаем таблицы
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        
        # Создаем фабрику сессий
        self.async_session = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False
        )
        
        logger.info(f"База данных инициализирована: {self.db_path}")
    
    async def close(self):
        """Закрытие соединения с базой данных"""
        if self.engine:
            await self.engine.dispose()
            logger.info("Соединение с базой данных закрыто")
    
    # ========== Работа с пользователями ==========
    
    async def get_user(self, telegram_id: int) -> Optional[User]:
        """Получить пользователя по telegram_id"""
        async with self.async_session() as session:
            result = await session.execute(
                select(User).where(User.telegram_id == telegram_id)
            )
            return result.scalar_one_or_none()

    async def get_all_telegram_ids(self) -> List[int]:
        """Получить все telegram_id пользователей (для рассылки)"""
        async with self.async_session() as session:
            result = await session.execute(select(User.telegram_id))
            return [row[0] for row in result.all()]

    async def get_users_count(self) -> int:
        """Получить количество пользователей"""
        async with self.async_session() as session:
            result = await session.execute(select(func.count(User.id)))
            return result.scalar() or 0
    
    async def create_or_update_user(
        self,
        telegram_id: int,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
        **kwargs
    ) -> User:
        """Создать или обновить пользователя"""
        async with self.async_session() as session:
            user = await self.get_user(telegram_id)
            
            if user:
                # Обновляем существующего пользователя
                for key, value in kwargs.items():
                    if hasattr(user, key) and value is not None:
                        setattr(user, key, value)
                if username:
                    user.username = username
                if first_name:
                    user.first_name = first_name
                user.updated_at = datetime.utcnow()
            else:
                # Создаем нового пользователя
                user = User(
                    telegram_id=telegram_id,
                    username=username,
                    first_name=first_name,
                    **kwargs
                )
                session.add(user)
            
            await session.commit()
            await session.refresh(user)
            return user
    
    # ========== Работа с сообщениями ==========
    
    async def add_message(self, user_id: int, role: str, content: str):
        """Добавить сообщение в историю"""
        async with self.async_session() as session:
            message = Message(
                user_id=user_id,
                role=role,
                content=content
            )
            session.add(message)
            await session.commit()
    
    async def get_user_messages(
        self,
        user_id: int,
        limit: int = 20
    ) -> List[Message]:
        """Получить последние сообщения пользователя"""
        async with self.async_session() as session:
            result = await session.execute(
                select(Message)
                .where(Message.user_id == user_id)
                .order_by(Message.created_at.desc())
                .limit(limit)
            )
            messages = result.scalars().all()
            return list(reversed(messages))  # Возвращаем в хронологическом порядке
    
    async def clear_user_messages(self, user_id: int):
        """Очистить историю сообщений пользователя"""
        async with self.async_session() as session:
            await session.execute(
                delete(Message).where(Message.user_id == user_id)
            )
            await session.commit()
    
    # ========== Работа со статистикой ==========
    
    async def get_stats(self, user_id: int) -> Optional[Stats]:
        """Получить статистику пользователя"""
        async with self.async_session() as session:
            result = await session.execute(
                select(Stats).where(Stats.user_id == user_id)
            )
            return result.scalar_one_or_none()
    
    async def update_stats(
        self,
        user_id: int,
        requests_count: Optional[int] = None,
        tokens_used: Optional[int] = None,
        images_generated: Optional[int] = None,
        command: Optional[str] = None
    ):
        """Обновить статистику пользователя"""
        async with self.async_session() as session:
            # Получаем статистику через текущую сессию
            result = await session.execute(
                select(Stats).where(Stats.user_id == user_id)
            )
            stats = result.scalar_one_or_none()
            
            if not stats:
                stats = Stats(user_id=user_id)
                session.add(stats)
                await session.flush()  # Получаем ID для нового объекта
            
            if requests_count is not None:
                stats.requests_count += requests_count
            if tokens_used is not None:
                stats.tokens_used += tokens_used
            if images_generated is not None:
                stats.images_generated += images_generated
            if command:
                commands = stats.commands_used or {}
                commands[command] = commands.get(command, 0) + 1
                stats.commands_used = commands
            
            stats.updated_at = datetime.utcnow()
            await session.commit()
    
    # ========== Работа с избранным ==========
    
    async def add_favorite(
        self,
        user_id: int,
        content: str,
        content_type: str = 'text',
        tags: Optional[List[str]] = None
    ) -> Favorite:
        """Добавить в избранное"""
        async with self.async_session() as session:
            favorite = Favorite(
                user_id=user_id,
                content=content,
                content_type=content_type,
                tags=tags or []
            )
            session.add(favorite)
            await session.commit()
            await session.refresh(favorite)
            return favorite
    
    async def get_user_favorites(
        self,
        user_id: int,
        limit: int = 50
    ) -> List[Favorite]:
        """Получить избранное пользователя"""
        async with self.async_session() as session:
            result = await session.execute(
                select(Favorite)
                .where(Favorite.user_id == user_id)
                .order_by(Favorite.created_at.desc())
                .limit(limit)
            )
            return list(result.scalars().all())
    
    # ========== Работа с достижениями ==========
    
    async def add_achievement(self, user_id: int, achievement_id: str):
        """Добавить достижение пользователю"""
        async with self.async_session() as session:
            # Проверяем, есть ли уже это достижение
            result = await session.execute(
                select(Achievement).where(
                    Achievement.user_id == user_id,
                    Achievement.achievement_id == achievement_id
                )
            )
            if result.scalar_one_or_none():
                return  # Достижение уже есть
            
            achievement = Achievement(
                user_id=user_id,
                achievement_id=achievement_id
            )
            session.add(achievement)
            await session.commit()
    
    async def get_user_achievements(self, user_id: int) -> List[str]:
        """Получить список достижений пользователя"""
        async with self.async_session() as session:
            result = await session.execute(
                select(Achievement.achievement_id)
                .where(Achievement.user_id == user_id)
            )
            return [row[0] for row in result.all()]


# Глобальный экземпляр базы данных
db = Database()
