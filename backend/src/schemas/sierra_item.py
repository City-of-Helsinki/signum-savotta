from pydantic import BaseModel

class SierraItem(BaseModel):
    item_record_id: int
    item_number: str
    barcode: str
    bib_number: str
    best_author: str
    best_title: str
    itype_code_num: int
    item_type_name: str
    material_code: str
    material_name: str
    paasana_json: str