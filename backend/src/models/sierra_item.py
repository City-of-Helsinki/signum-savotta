from typing import Any, Optional

import regex
import uroman as ur
from models.base import Base
from sqlalchemy import JSON, BigInteger, SmallInteger, String, Text
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, mapped_column

uroman = ur.Uroman()


def signumize(cls, content, skip=0):
    cleaned = regex.sub(r"[^\p{Latin}0-9]", "", content[skip : len(content)]).capitalize()
    if len(cleaned) == 0:
        cleaned = regex.sub(
            r"[^\p{Latin}0-9]",
            "",
            str(
                cls.uroman.romanize_string(
                    s=content[skip : len(content)], rom_format=ur.RomFormat.STR
                )
            ),
        ).capitalize()
        if len(cleaned) == 0:
            raise AttributeError("Signum is empty.")
    return cleaned[0 : 3 if len(cleaned) >= 3 else len(cleaned)]


class SierraItem(Base):
    __tablename__ = "sierra_item"
    item_record_id: Mapped[int] = mapped_column("item_record_id", BigInteger, primary_key=True)
    item_number: Mapped[str] = mapped_column("item_number", Text)
    barcode: Mapped[Optional[str]] = mapped_column("barcode", String(1000))
    bib_number: Mapped[str] = mapped_column("bib_number", Text)
    bib_record_id: Mapped[int] = mapped_column("bib_record_id", BigInteger)
    best_author: Mapped[Optional[str]] = mapped_column("best_author", String(1000))
    best_title: Mapped[Optional[str]] = mapped_column("best_title", String(1000))
    itype_code_num: Mapped[Optional[int]] = mapped_column("itype_code_num", SmallInteger)
    item_type_name: Mapped[Optional[str]] = mapped_column("item_type_name", String(255))
    material_code: Mapped[Optional[str]] = mapped_column("material_code", String(3))
    material_name: Mapped[Optional[str]] = mapped_column("material_name", String(255))
    paasana_json: Mapped[dict[str, Any]] = mapped_column("paasana_json", JSON)

    @hybrid_property
    def paasana(self) -> str:
        try:
            for field in self.paasana_json:
                if field["marc_tag"] == "100" and field["tag"] == "a" and field["marc_ind1"] == "1":
                    try:
                        return signumize(field["content"], 0)
                    except Exception:
                        pass
            for field in self.paasana_json:
                if field["marc_tag"] == "110" and field["tag"] == "a" and field["marc_ind1"] == "2":
                    try:
                        return signumize(field["content"], 0)
                    except Exception:
                        pass
            for field in self.paasana_json:
                if field["marc_tag"] == "100" and field["tag"] == "a" and field["marc_ind1"] == "0":
                    try:
                        return signumize(field["content"], 0)
                    except Exception:
                        pass
            for field in self.paasana_json:
                if field["marc_tag"] == "100" and field["tag"] == "a" and field["marc_ind1"] == "2":
                    try:
                        return signumize(field["content"], 0)
                    except Exception:
                        pass
            for field in self.paasana_json:
                if field["marc_tag"] == "110" and field["tag"] == "a" and field["marc_ind1"] == "1":
                    try:
                        return signumize(field["content"], 0)
                    except Exception:
                        pass
            for field in self.paasana_json:
                if field["marc_tag"] == "110" and field["tag"] == "a" and field["marc_ind1"] == "0":
                    try:
                        return signumize(field["content"], 0)
                    except Exception:
                        pass

            for field in self.paasana_json:
                if field["marc_tag"] == "100" and field["tag"] == "a" and field["marc_ind1"] == "3":
                    try:
                        return signumize(field["content"], 0)
                    except Exception:
                        pass
            for field in self.paasana_json:
                if field["marc_tag"] == "111" and field["tag"] == "a" and field["marc_ind1"] == "0":
                    try:
                        return signumize(field["content"], 0)
                    except Exception:
                        pass

            for field in self.paasana_json:
                if field["marc_tag"] == "111" and field["tag"] == "a" and field["marc_ind1"] == "1":
                    try:
                        return signumize(field["content"], 0)
                    except Exception:
                        pass
            for field in self.paasana_json:
                if field["marc_tag"] == "111" and field["tag"] == "a" and field["marc_ind1"] == "2":
                    try:
                        return signumize(field["content"], 0)
                    except Exception:
                        pass
            for field in self.paasana_json:
                if field["marc_tag"] == "245" and field["tag"] == "a" and field["marc_ind1"] == "0":
                    try:
                        skip = int(field["marc_ind2"])
                        return signumize(field["content"], skip)
                    except Exception:
                        pass
            for field in self.paasana_json:
                if field["marc_tag"] == "245" and field["tag"] == "a" and field["marc_ind1"] == "1":
                    try:
                        skip = int(field["marc_ind2"])
                        return signumize(field["content"], skip)
                    except Exception:
                        pass
            for field in self.paasana_json:
                if field["marc_tag"] == "245" and field["tag"] == "a":
                    try:
                        skip = int(field["marc_ind2"])
                        return signumize(field["content"], skip)
                    except Exception:
                        pass
            for field in self.paasana_json:
                if field["marc_tag"] == "245" and field["tag"] == "a":
                    try:
                        return signumize(field["content"], 0)
                    except Exception:
                        pass
        except Exception:
            pass

        return "***"
