from __future__ import annotations

from typing import Any, List

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncAttrs, AsyncSession
from sqlalchemy.inspection import inspect
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.types import JSON


class Base(AsyncAttrs, DeclarativeBase):
    """
    Base
    """

    type_annotation_map = {
        dict[str, Any]: JSON,
    }
    pass

    # Override index_columns in classes that inherit this class
    index_columns: List[str] = []

    @classmethod
    async def upsert_batch(
        cls,
        session: AsyncSession,
        dicts: List[dict],
        return_upserted: bool = False,
    ):
        """
        Performs a batch upsert (insert or update) of the provided dictionaries into the database.

        This method splits the input list of dictionaries into batches to avoid exceeding PostgreSQL's
        parameter limit (32,767). Each batch is inserted using a PostgreSQL `ON CONFLICT DO UPDATE`
        clause, which updates existing records based on the `item_record_id` primary key.

        Args:
            session (AsyncSession): The SQLAlchemy asynchronous session used for database operations.
            dicts (List[dict]): A list of dictionaries representing SierraItem records to be upserted.
            return_upserted (bool, optional): If True, returns the upserted records. Defaults to False.

        Returns:
            Optional[List[cls]]: A list of upserted ORM objects if `return_upserted` is True, otherwise None.

        Note:
            - The method does not return the upserted objects.
            - This method assumes that `item_record_id` is the unique identifier for conflict resolution.
        """

        mapper = inspect(cls)
        max_dicts_per_batch = 32767 // len(mapper.attrs)
        batches = [
            dicts[i : i + max_dicts_per_batch] for i in range(0, len(dicts), max_dicts_per_batch)
        ]

        for batch in batches:
            stmt = insert(cls).values(batch)
            stmt = stmt.on_conflict_do_update(
                index_elements=[getattr(cls, col) for col in cls.index_columns],
                set_={
                    col.name: stmt.excluded[col.name]
                    for col in cls.__table__.columns
                    if col.name not in cls.index_columns
                },
            ).returning(cls)
            if return_upserted:
                orm_stmt = (
                    select(cls).from_statement(stmt).execution_options(populate_existing=True)
                )
                result = await session.execute(orm_stmt)
                return await result.scalars().all()
            else:
                await session.execute(stmt)
                return None
