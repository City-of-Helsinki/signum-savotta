"""
SQLAlchemy model for backend application state persistence
"""

import enum
from datetime import datetime
from typing import Optional, Self

from models.base import Base
from sqlalchemy import (
    Boolean,
    Column,
    Computed,
    DateTime,
    Enum,
    Integer,
    select,
    update,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.inspection import inspect
from sqlalchemy.orm import Mapped, mapped_column


class SyncMode(enum.Enum):
    """
    SyncMode
    """

    SYNC_FULL = "sync_full"
    SYNC_CHANGES = "sync_changes"


class BackendState(Base):
    """
    BackendState defines a singleton table where only one row exists
    """

    __tablename__ = "backend_state"

    id = Column(Integer, primary_key=True, autoincrement=True)
    lock = Column(Boolean, Computed("TRUE", persisted=True), unique=True)

    initialized_at: Mapped[Optional[datetime]] = mapped_column(
        "initialized_at", DateTime(timezone=True)
    )

    sync_mode: Mapped[Optional[SyncMode]] = mapped_column("sync_mode", Enum(SyncMode))

    full_sync_completed_at: Mapped[Optional[datetime]] = mapped_column(
        "full_sync_completed_at", DateTime(timezone=True)
    )

    sync_changes_since: Mapped[Optional[datetime]] = mapped_column(
        "sync_changes_since", DateTime(timezone=True)
    )

    last_sync_run_completed_at: Mapped[Optional[datetime]] = mapped_column(
        "last_sync_run_completed_at", DateTime(timezone=True)
    )

    @classmethod
    async def upsert_singleton(cls, session: AsyncSession, instance: Self) -> Self:
        """
        upsert_singleton
        """
        result = await session.execute(select(cls))
        value: Self = result.scalar_one_or_none()
        if not value:
            session.add(instance)
        else:
            mapper = inspect(cls)
            values = {
                attr.key: getattr(instance, attr.key)
                for attr in mapper.attrs
                if attr.key not in ("id", "lock") and getattr(instance, attr.key) is not None
            }
            if values:
                stmt = (
                    update(cls)
                    .where(cls.lock == True)  # noqa
                    .values(**values)
                    .execution_options(synchronize_session="fetch")
                )
                await session.execute(stmt)
        result = await session.execute(select(cls).where(cls.lock == True))  # noqa
        return result.scalar_one()
