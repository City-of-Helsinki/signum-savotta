"""
SQLAlchemy ORM base module with asynchronous support and PostgreSQL-specific utilities.
"""

from __future__ import annotations

from typing import Any, List

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncAttrs, AsyncSession
from sqlalchemy.inspection import inspect
from sqlalchemy.orm import DeclarativeBase, Mapper
from sqlalchemy.types import JSON


class Base(AsyncAttrs, DeclarativeBase):
    """
    Base class for all ORM models using SQLAlchemy 2.0 with asynchronous support.

    This class combines SQLAlchemy's `DeclarativeBase` for declarative model definitions
    with `AsyncAttrs` to enable asynchronous operations on ORM instances.

    Features:
    ---------
    - Defines a custom `type_annotation_map` to automatically map Python `dict[str, Any]`
      annotations to PostgreSQL's `JSON` type.
    - Provides a reusable `upsert_batch` class method for efficient bulk upserts using
      PostgreSQL's `ON CONFLICT DO UPDATE` clause.
    - Handles batching to avoid exceeding PostgreSQL's parameter limit when using asyncpg.

    Usage:
    ------
    Subclass this `Base` to define your ORM models. Use `upsert_batch` to insert or update
    multiple records asynchronously in a single transaction.

    Example:
    --------
    class MyModel(Base):
        __tablename__ = "my_table"
        id = Column(Integer, primary_key=True)
        data = Column(JSON)

    await MyModel.upsert_batch(session, [{"id": 1, "data": {...}}, ...])
    """

    type_annotation_map = {
        dict[str, Any]: JSON,
    }

    @classmethod
    async def upsert_batch(
        cls, session: AsyncSession, dicts: List[dict], return_upserted: bool = False
    ):
        """
        Performs a batch upsert (insert or update) of the provided dictionaries into the database.

        This method splits the input list of dictionaries into batches to avoid exceeding asyncpg
        parameter limit (32,767). Each batch is inserted using a PostgreSQL `ON CONFLICT DO UPDATE`
        clause, which updates existing records based on the index columns.

        Args:
            session (AsyncSession): The SQLAlchemy asynchronous session used for database operations.
            dicts (List[dict]): A list of dictionaries representing SierraItem records to be upserted.
            return_upserted (bool, optional): If True, returns the upserted records. Defaults to False.

        Returns:
            Optional[List[cls]]: A list of upserted ORM objects if `return_upserted` is True, otherwise None.
        """

        mapper: Mapper = inspect(cls)
        # FIXME: PostgreSQL has a native parameter limit of 65535. Update if asyncpg starts to support it.
        max_dicts_per_batch = 32767 // len(mapper.columns)
        batches = [
            dicts[i : i + max_dicts_per_batch] for i in range(0, len(dicts), max_dicts_per_batch)
        ]
        upserted = []
        for batch in batches:
            stmt = insert(cls).values(batch)
            stmt = stmt.on_conflict_do_update(
                index_elements=[getattr(cls, col.name) for col in mapper.primary_key],
                set_={
                    col.name: stmt.excluded[col.name]
                    for col in mapper.columns
                    if col not in mapper.primary_key
                },
            )
            if return_upserted:
                orm_stmt = (
                    select(cls)
                    .from_statement(stmt.returning(cls))
                    .execution_options(populate_existing=True)
                )
                result = await session.execute(orm_stmt)
                upserted.append(result.scalars().all())
            else:
                await session.execute(stmt)
        if return_upserted:
            return upserted
        else:
            return None
