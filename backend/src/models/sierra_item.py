"""
SQLAlchemy model for item data synchronized from Sierra via ETL component
"""

import json
import logging
from typing import Optional

import regex
import uroman as ur
from models.base import Base
from sqlalchemy import JSON, BigInteger, Index, SmallInteger, String, Text
from sqlalchemy.ext.hybrid import hybrid_property
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
    classification: Mapped[Optional[str]] = mapped_column("classification", String(16))
    paasana_json: Mapped[Optional[str]] = mapped_column("paasana_json", JSON)

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
