from datetime import datetime
from typing import Any

import models.client
from models.base import Base
from sqlalchemy import JSON, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship


class ClientStatusReport(Base):
    client: Mapped["src.models.client.Client"] = relationship(
        "src.models.client.Client",
        foreign_keys="src.models.client.Client.id",
        back_populates="status_reports",
        lazy="joined",
    )
    reporting_time: Mapped[datetime] = mapped_column("reporting_time", DateTime)
    report_json: Mapped[dict[str, Any]] = mapped_column("report_json", JSON)
