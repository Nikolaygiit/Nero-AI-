"""
Работа с базой данных SQLite через aiosqlite
"""

import logging
from datetime import datetime, timezone
from typing import Any, List, Optional

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from .models import (
    Achievement,
    Base,
    Favorite,
    Message,
    Stats,
    Subscription,
    UsageDaily,
    User,
    UserFact,
)

logger = logging.getLogger(__name__)

# Путь к базе данных
DB_PATH = "bot_database.db"


class Database:
    """Класс для работы с базой данных"""

    engine: AsyncEngine | None
    async_session: async_sessionmaker[AsyncSession] | None

    def __init__(self, db_path: str = DB_PATH) -> None:
        self.db_path = db_path
        self.engine: AsyncEngine | None = None
        self.async_session: async_sessionmaker[AsyncSession] | None = None

    async def init(self) -> None:
        """Инициализация базы данных"""
        # Создаем асинхронный движок SQLite
        self.engine = create_async_engine(f"sqlite+aiosqlite:///{self.db_path}", echo=False)

        # Создаем таблицы
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        # Создаем фабрику сессий
        self.async_session = async_sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)

        logger.info(f"База данных инициализирована: {self.db_path}")

    async def close(self) -> None:
        """Закрытие соединения с базой данных"""
        if self.engine:
            await self.engine.dispose()
            logger.info("Соединение с базой данных закрыто")

    # ========== Работа с пользователями ==========

    async def get_user(self, telegram_id: int) -> Optional[User]:
        """Получить пользователя по telegram_id"""
        async with self.async_session() as session:
            result = await session.execute(select(User).where(User.telegram_id == telegram_id))
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
        **kwargs: Any,
    ) -> User:
        """Создать или обновить пользователя"""
        async with self.async_session() as session:
            result = await session.execute(select(User).where(User.telegram_id == telegram_id))
            user = result.scalar_one_or_none()

            if user:
                # Обновляем существующего пользователя
                for key, value in kwargs.items():
                    if hasattr(user, key) and value is not None:
                        setattr(user, key, value)
                if username:
                    user.username = username
                if first_name:
                    user.first_name = first_name
                user.updated_at = datetime.now(timezone.utc)
            else:
                # Создаем нового пользователя
                user = User(telegram_id=telegram_id, username=username, first_name=first_name, **kwargs)
                session.add(user)

            await session.commit()
            await session.refresh(user)
            return user

    # ========== Работа с сообщениями ==========

    async def add_message(self, user_id: int, role: str, content: str) -> None:
        """Добавить сообщение в историю"""
        async with self.async_session() as session:
            message = Message(user_id=user_id, role=role, content=content)
            session.add(message)
            await session.commit()

    async def get_user_messages(self, user_id: int, limit: int = 20) -> List[Message]:
        """Получить последние сообщения пользователя"""
        async with self.async_session() as session:
            result = await session.execute(
                select(Message).where(Message.user_id == user_id).order_by(Message.created_at.desc()).limit(limit)
            )
            messages = result.scalars().all()
            return list(reversed(messages))  # Возвращаем в хронологическом порядке

    async def clear_user_messages(self, user_id: int) -> None:
        """Очистить историю сообщений пользователя"""
        async with self.async_session() as session:
            await session.execute(delete(Message).where(Message.user_id == user_id))
            await session.commit()

    # ========== Работа со статистикой ==========

    async def get_stats(self, user_id: int) -> Optional[Stats]:
        """Получить статистику пользователя"""
        async with self.async_session() as session:
            result = await session.execute(select(Stats).where(Stats.user_id == user_id))
            return result.scalar_one_or_none()

    async def update_stats(
        self,
        user_id: int,
        requests_count: Optional[int] = None,
        tokens_used: Optional[int] = None,
        images_generated: Optional[int] = None,
        command: Optional[str] = None,
    ) -> None:
        """Обновить статистику пользователя"""
        async with self.async_session() as session:
            # Получаем статистику через текущую сессию
            result = await session.execute(select(Stats).where(Stats.user_id == user_id))
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

            stats.updated_at = datetime.now(timezone.utc)
            await session.commit()

    # ========== Работа с избранным ==========

    async def add_favorite(
        self, user_id: int, content: str, content_type: str = "text", tags: Optional[List[str]] = None
    ) -> Favorite:
        """Добавить в избранное"""
        async with self.async_session() as session:
            favorite = Favorite(user_id=user_id, content=content, content_type=content_type, tags=tags or [])
            session.add(favorite)
            await session.commit()
            await session.refresh(favorite)
            return favorite

    async def get_user_favorites(self, user_id: int, limit: int = 50) -> List[Favorite]:
        """Получить избранное пользователя"""
        async with self.async_session() as session:
            result = await session.execute(
                select(Favorite).where(Favorite.user_id == user_id).order_by(Favorite.created_at.desc()).limit(limit)
            )
            return list(result.scalars().all())

    # ========== Работа с достижениями ==========

    async def add_achievement(self, user_id: int, achievement_id: str) -> None:
        """Добавить достижение пользователю"""
        async with self.async_session() as session:
            # Проверяем, есть ли уже это достижение
            result = await session.execute(
                select(Achievement).where(Achievement.user_id == user_id, Achievement.achievement_id == achievement_id)
            )
            if result.scalar_one_or_none():
                return  # Достижение уже есть

            achievement = Achievement(user_id=user_id, achievement_id=achievement_id)
            session.add(achievement)
            await session.commit()

    async def get_user_achievements(self, user_id: int) -> List[str]:
        """Получить список достижений пользователя"""
        async with self.async_session() as session:
            result = await session.execute(select(Achievement.achievement_id).where(Achievement.user_id == user_id))
            return [row[0] for row in result.all()]

    # ========== RAG Lite: факты о пользователе ==========

    async def add_user_fact(self, user_id: int, fact_type: str, fact_value: str) -> None:
        """Добавить факт о пользователе (дедупликация по типу: храним последний)"""
        async with self.async_session() as session:
            result = await session.execute(
                select(UserFact).where(
                    UserFact.user_id == user_id,
                    UserFact.fact_type == fact_type,
                )
            )
            existing = result.scalar_one_or_none()
            if existing:
                existing.fact_value = fact_value
            else:
                session.add(UserFact(user_id=user_id, fact_type=fact_type, fact_value=fact_value))
            await session.commit()

    async def get_user_facts(self, user_id: int, limit: int = 5) -> List[UserFact]:
        """Получить последние факты пользователя"""
        async with self.async_session() as session:
            result = await session.execute(
                select(UserFact).where(UserFact.user_id == user_id).order_by(UserFact.created_at.desc()).limit(limit)
            )
            return list(result.scalars().all())

    # ========== Подписка и лимиты ==========

    async def is_premium(self, user_id: int) -> bool:
        """Проверка премиум-подписки"""
        async with self.async_session() as session:
            result = await session.execute(
                select(Subscription).where(
                    Subscription.user_id == user_id,
                    Subscription.tier == "premium",
                )
            )
            return result.scalar_one_or_none() is not None

    async def get_daily_usage(self, user_id: int, date_str: str) -> int:
        """Получить количество запросов за день"""
        async with self.async_session() as session:
            result = await session.execute(
                select(UsageDaily).where(
                    UsageDaily.user_id == user_id,
                    UsageDaily.date == date_str,
                )
            )
            row = result.scalar_one_or_none()
            return row.count if row else 0

    async def increment_daily_usage(self, user_id: int, date_str: str) -> int:
        """Увеличить счётчик за день, вернуть новое значение"""
        async with self.async_session() as session:
            result = await session.execute(
                select(UsageDaily).where(
                    UsageDaily.user_id == user_id,
                    UsageDaily.date == date_str,
                )
            )
            row = result.scalar_one_or_none()
            if row:
                row.count += 1
                count = row.count
            else:
                session.add(UsageDaily(user_id=user_id, date=date_str, count=1))
                count = 1
            await session.commit()
            return count

    async def set_premium(self, user_id: int) -> None:
        """Установить премиум-подписку"""
        async with self.async_session() as session:
            result = await session.execute(select(Subscription).where(Subscription.user_id == user_id))
            sub = result.scalar_one_or_none()
            if sub:
                sub.tier = "premium"
                sub.stars_paid_at = datetime.now(timezone.utc)
            else:
                session.add(Subscription(user_id=user_id, tier="premium"))
            await session.commit()

    async def remove_premium(self, user_id: int) -> None:
        """Снять премиум-подписку"""
        async with self.async_session() as session:
            result = await session.execute(select(Subscription).where(Subscription.user_id == user_id))
            sub = result.scalar_one_or_none()
            if sub:
                sub.tier = "free"
                sub.stars_paid_at = None
                await session.commit()

    async def ban_user(self, telegram_id: int) -> None:
        """Забанить пользователя"""
        async with self.async_session() as session:
            result = await session.execute(select(User).where(User.telegram_id == telegram_id))
            user = result.scalar_one_or_none()
            if user:
                user.is_banned = True
                await session.commit()

    async def unban_user(self, telegram_id: int) -> None:
        """Разбанить пользователя"""
        async with self.async_session() as session:
            result = await session.execute(select(User).where(User.telegram_id == telegram_id))
            user = result.scalar_one_or_none()
            if user:
                user.is_banned = False
                await session.commit()

    async def is_banned(self, telegram_id: int) -> bool:
        """Проверить, забанен ли пользователь"""
        async with self.async_session() as session:
            result = await session.execute(select(User.is_banned).where(User.telegram_id == telegram_id))
            row = result.scalar_one_or_none()
            return bool(row) if row is not None else False


# Глобальный экземпляр базы данных
db = Database()
