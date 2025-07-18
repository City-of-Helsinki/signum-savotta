from sqlalchemy import Mapped, Column, Integer, Float, Date
class BackendState():
    key: Mapped[str] = mapped_column(unique=True)
    
