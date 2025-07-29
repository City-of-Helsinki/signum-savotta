import enum
from datetime import datetime
from typing import List, Optional

from models.base import Base
from sqlalchemy import BigInteger, DateTime, Enum, Index, String
from sqlalchemy.orm import Mapped, mapped_column


class ClientType(enum.Enum):
    ETL = "etl"
    SIGNUM_PRINTER = "signum-printer"


class Client(Base):
    __tablename__ = "client"
    __table_args__ = (Index("ix_api_key", "api_key", postgresql_using="hash"),)

    id: Mapped[int] = mapped_column("id", BigInteger, primary_key=True)
    client_name: Mapped[str] = mapped_column("client_name", String(255), unique=True)
    client_type: Mapped[ClientType] = mapped_column("client_type", Enum(ClientType))
    api_key: Mapped[str] = mapped_column("api_key", String(128), unique=True)

    internal_ip_address: Mapped[Optional[str]] = mapped_column("internal_ip_address", String(255))
    internal_hostname: Mapped[Optional[str]] = mapped_column("internal_hostname", String(255))
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(
        "last_seen_at", DateTime(timezone=True)
    )

    index_columns: List[str] = ["id"]
