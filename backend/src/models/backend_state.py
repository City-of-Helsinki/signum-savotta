"""
SQLAlchemy model for backend application state persistence
"""

from datetime import datetime
from typing import Optional, Self

from models.base import Base
from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Computed,
    DateTime,
    Integer,
    select,
    update,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.inspection import inspect
from sqlalchemy.orm import Mapped, mapped_column


class BackendState(Base):
    """
    BackendState defines a singleton table where only one row exists
    """

    __tablename__ = "backend_state"

    id = Column(Integer, primary_key=True, autoincrement=True)
    lock = Column(Boolean, Computed("TRUE", persisted=True), unique=True)

    initial_sync_complete: Mapped[Optional[bool]] = mapped_column("initial_sync_complete", Boolean)
    start_next_sync_from_zero: Mapped[Optional[bool]] = mapped_column(
        "start_next_sync_from_zero", Boolean
    )
    last_sync_complete: Mapped[Optional[datetime]] = mapped_column("last_sync_completed", DateTime)
    last_full_sync_completed: Mapped[Optional[datetime]] = mapped_column(
        "last_full_sync_completed", DateTime
    )
    last_synced_sierra_item_id: Mapped[Optional[int]] = mapped_column(
        "last_synced_sierra_item_id", BigInteger
    )

    @classmethod
    async def upsert_singleton(cls, session: AsyncSession, instance: Self) -> Self:
        try:
            async with session.begin():
                session.add(instance)
        except IntegrityError:
            await session.rollback()
            mapper = inspect(cls)
            values = {
                attr.key: getattr(instance, attr.key)
                for attr in mapper.attrs
                if attr.key not in ("id", "lock") and getattr(instance, attr.key) is not None
            }

            if values:
                async with session.begin():
                    stmt = (
                        update(cls)
                        .where(cls.lock == True)  # noqa
                        .values(**values)
                        .execution_options(synchronize_session="fetch")
                    )
                    await session.execute(stmt)
        async with session.begin():
            result = await session.execute(select(cls).where(cls.lock == True))  # noqa
            return result.scalar_one()
