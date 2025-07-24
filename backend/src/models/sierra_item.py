"""
SQLAlchemy model for item data synchronized from Sierra via ETL component
"""

import json
import logging
from datetime import datetime
from typing import List, Optional

import regex
import uroman as ur
from models.base import Base
from sqlalchemy import JSON, BigInteger, DateTime, Index, SmallInteger, String, Text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.inspection import inspect
from sqlalchemy.orm import Mapped, mapped_column

uroman = ur.Uroman()
logger = logging.getLogger()


def signumize(content, skip=0):
    """
    signumize
    """
    content = f"{content}"
    cleaned = regex.sub(r"[^\p{Latin}0-9]", "", content[skip : len(content)]).capitalize()
    if len(cleaned) == 0:
        cleaned = regex.sub(
            r"[^\p{Latin}0-9]",
            "",
            str(ur.romanize_string(s=content[skip : len(content)], rom_format=ur.RomFormat.STR)),
        ).capitalize()
        if len(cleaned) == 0:
            raise AttributeError("Signum is empty.")
    return f"{cleaned[0 : 3 if len(cleaned) >= 3 else len(cleaned)]}"


class SierraItem(Base):
    """
    SierraItem
    """

    __tablename__ = "sierra_item"
    __table_args__ = (Index("ix_barcode", "barcode", postgresql_using="hash"),)

    item_record_id: Mapped[int] = mapped_column("item_record_id", BigInteger, primary_key=True)
    item_number: Mapped[Optional[str]] = mapped_column("item_number", Text)
    barcode: Mapped[Optional[str]] = mapped_column("barcode", String(1000))
    bib_number: Mapped[Optional[str]] = mapped_column("bib_number", Text)
    bib_record_id: Mapped[Optional[int]] = mapped_column("bib_record_id", BigInteger)
    best_author: Mapped[Optional[str]] = mapped_column("best_author", String(1000))
    best_title: Mapped[Optional[str]] = mapped_column("best_title", String(1000))
    itype_code_num: Mapped[Optional[int]] = mapped_column("itype_code_num", SmallInteger)
    item_type_name: Mapped[Optional[str]] = mapped_column("item_type_name", String(255))
    material_code: Mapped[Optional[str]] = mapped_column("material_code", String(3))
    material_name: Mapped[Optional[str]] = mapped_column("material_name", String(255))
    classification: Mapped[Optional[str]] = mapped_column("classification", Text)
    paasana_json: Mapped[Optional[str]] = mapped_column("paasana_json", JSON)
    updated_at: Mapped[datetime] = mapped_column("updated_at", DateTime(timezone=True))

    @hybrid_property
    def paasana(self) -> str:
        """
        paasana
        """
        fieldlist = []
        if self.paasana_json is not None and self.paasana_json != "":
            preprocessed = regex.sub(r"(?<={| )'", r'"', self.paasana_json)
            preprocessed = regex.sub(r"'(?=[:,}])", r'"', preprocessed)
            fieldlist = json.loads(preprocessed)

        for field in fieldlist:
            if field["marc_tag"] == "100" and field["tag"] == "a" and field["marc_ind1"] == "1":
                return signumize(field["content"], 0)
        for field in fieldlist:
            if field["marc_tag"] == "110" and field["tag"] == "a" and field["marc_ind1"] == "2":
                return signumize(field["content"], 0)
        for field in fieldlist:
            if field["marc_tag"] == "100" and field["tag"] == "a" and field["marc_ind1"] == "0":
                return signumize(field["content"], 0)
        for field in fieldlist:
            if field["marc_tag"] == "100" and field["tag"] == "a" and field["marc_ind1"] == "2":
                return signumize(field["content"], 0)
        for field in fieldlist:
            if field["marc_tag"] == "110" and field["tag"] == "a" and field["marc_ind1"] == "1":
                return signumize(field["content"], 0)
        for field in fieldlist:
            if field["marc_tag"] == "110" and field["tag"] == "a" and field["marc_ind1"] == "0":
                return signumize(field["content"], 0)
        for field in fieldlist:
            if field["marc_tag"] == "100" and field["tag"] == "a" and field["marc_ind1"] == "3":
                return signumize(field["content"], 0)
        for field in fieldlist:
            if field["marc_tag"] == "111" and field["tag"] == "a" and field["marc_ind1"] == "0":
                return signumize(field["content"], 0)
        for field in fieldlist:
            if field["marc_tag"] == "111" and field["tag"] == "a" and field["marc_ind1"] == "1":
                return signumize(field["content"], 0)
        for field in fieldlist:
            if field["marc_tag"] == "111" and field["tag"] == "a" and field["marc_ind1"] == "2":
                return signumize(field["content"], 0)
        for field in fieldlist:
            if field["marc_tag"] == "245" and field["tag"] == "a" and field["marc_ind1"] == "0":
                skip = int(field["marc_ind2"])
                return signumize(field["content"], skip)
        for field in fieldlist:
            if field["marc_tag"] == "245" and field["tag"] == "a" and field["marc_ind1"] == "1":
                skip = int(field["marc_ind2"])
                return signumize(field["content"], skip)
        for field in fieldlist:
            if field["marc_tag"] == "245" and field["tag"] == "a":
                skip = int(field["marc_ind2"])
                return signumize(field["content"], skip)
        for field in fieldlist:
            if field["marc_tag"] == "245" and field["tag"] == "a":
                return signumize(field["content"], 0)

        return "***"

    @classmethod
    async def upsert_dicts_batch(cls, session: AsyncSession, dicts: List[dict]):
        """
        upsert_dicts_batch
        """

        mapper = inspect(cls)
        max_dicts_per_batch = 32767 // len(mapper.attrs)
        batches = [
            dicts[i : i + max_dicts_per_batch] for i in range(0, len(dicts), max_dicts_per_batch)
        ]

        for batch in batches:
            stmt = insert(cls).values(batch)
            stmt = stmt.on_conflict_do_update(
                index_elements=[SierraItem.item_record_id],
                set_={
                    col.name: stmt.excluded[col.name]
                    for col in cls.__table__.columns
                    if col.name != "item_record_id"
                },
            ).returning(cls)
            orm_stmt = select(cls).from_statement(stmt).execution_options(populate_existing=True)
            await session.execute(orm_stmt)
