from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncAttrs
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
