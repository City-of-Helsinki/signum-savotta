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
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, mapped_column

uroman = ur.Uroman()
logger = logging.getLogger()


def signumize(content, skip=0):
    """
    Creates a three-letter string for signum stickers, used for alphabetic sorting.

    Args:
        content (str): The input string to process.
        skip (int): Number of characters to skip from the beginning.

    Returns:
        str: A cleaned, capitalized string of up to three characters.

    Raises:
        AttributeError: If no valid characters are found.
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
    Represents an item record synchronized from the Sierra library system, including bibliographic
    and classification metadata.

    This model maps to the `sierra_item` table in the database and includes fields such as item
    identifiers, bibliographic references, material types, and classification data. It also provides
    a hybrid property `shelfmark` for generating a three-letter alphabetic sorting key based on MARC
    metadata, and a class method `upsert_batch` for efficient batch upsert operations.

    Attributes:
        item_record_id (int): Primary key. Unique identifier for the item record.
        item_number (Optional[str]): Human-readable item number.
        barcode (Optional[str]): Barcode associated with the item.
        bib_number (Optional[str]): Bibliographic number linked to the item.
        bib_record_id (Optional[int]): Foreign key to the bibliographic record.
        best_author (Optional[str]): Best guess of the author name.
        best_title (Optional[str]): Best guess of the title.
        itype_code_num (Optional[int]): Item type code (numeric).
        item_type_name (Optional[str]): Human-readable item type name.
        material_code (Optional[str]): Material type code.
        material_name (Optional[str]): Human-readable material type name.
        classification (Optional[str]): Classification string.
        shelfmark_json (Optional[str]): JSON-encoded MARC metadata used to derive
            the three-letter alphabetic sorting string (pääsana).
        updated_at (datetime): Timestamp of the last update.
        times_printed (int): Times the signum has been printed

    Hybrid Properties:
        shelfmark (str): A three-letter string used for alphabetic sorting, derived from MARC fields.

    Class Methods:
        upsert_batch(session: AsyncSession, dicts: List[dict]):
            Performs a batch upsert of item records into the database using PostgreSQL's
            ON CONFLICT DO UPDATE clause.

    Indexes:
        ix_barcode: Hash index on the `barcode` column for fast lookups.
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
    shelfmark_json: Mapped[Optional[str]] = mapped_column("shelfmark_json", JSON)
    updated_at: Mapped[datetime] = mapped_column("updated_at", DateTime(timezone=True))
    times_printed: Mapped[int] = mapped_column("times_printed", SmallInteger, default=0)

    @hybrid_property
    def shelfmark(self) -> str:
        """
        Returns a three-letter alphabetic sorting key for shelfmark derived from MARC fields.

        This property parses the `shelfmark_json` field, which contains MARC metadata in JSON format.
        It searches for specific MARC tags and indicators in a prioritized order to extract the most
        relevant content for sorting. The extracted content is then cleaned and truncated to a
        three-character string using the `signumize` function.

        Returns:
            str: A three-letter string used for alphabetic sorting. Returns '***' if no valid content is found.

        Raises:
            AttributeError: If `signumize` fails to generate a valid string from the content.
        """

        if not self.shelfmark_json:
            return "***"

        try:
            fieldlist = []
            if self.shelfmark_json is not None and self.shelfmark_json != "":
                preprocessed = regex.sub(r"(?<={| )'", r'"', self.shelfmark_json)
                preprocessed = regex.sub(r"'(?=[:,}])", r'"', preprocessed)
                fieldlist = json.loads(preprocessed)
        except Exception:
            return "***"
        """
        FIXME: This could be refactored to priority list instead to avoid multiple loops.
        However, having the multiple loops makes it easier to change logic of one case without need to
        add flags to priority list.
        """
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
