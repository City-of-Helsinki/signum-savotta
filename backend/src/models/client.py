from typing import List

from models.base import Base
from sqlalchemy import BigInteger, String
from sqlalchemy.orm import Mapped, mapped_column, relationship


class Client(Base):
    __tablename__ = "client"
    id: Mapped[int] = mapped_column("id", BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column("id", String(255), unique=True)
    api_key: Mapped[str] = mapped_column("id", String(255))
    status_reports: Mapped[List["src.models.client_status_report.ClientStatusReport"]] = (
        relationship(
            "src.models.client_status_report.ClientStatusReport",
            back_populates="client",
            lazy="select",
        )
    )
