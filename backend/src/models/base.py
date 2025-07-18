from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.types import JSON
from typing import Any


class Base(AsyncAttrs, DeclarativeBase):
    type_annotation_map = {
        dict[str, Any]: JSON,
    }
    pass