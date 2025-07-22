"""
Pydantic models for Sierra item
"""

from typing import Optional

from pydantic import BaseModel


class SierraItemBase(BaseModel):
    item_record_id: int
    item_number: str
    barcode: str
    bib_number: str
    best_author: Optional[str]
    best_title: Optional[str]
    itype_code_num: Optional[int]
    item_type_name: Optional[str]
    material_code: Optional[str]
    material_name: Optional[str]
    classification: str
    paasana: str


class SierraItem(SierraItemBase):
    item_record_id: int

    class Config:
        from_attributes = True
