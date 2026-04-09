import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import uuid
from datetime import date, datetime

from sqlalchemy import Column, Date, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import relationship

from database import Base


class TimeEntry(Base):
    __tablename__ = "time_entries"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    ticket_id = Column(String(36), ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    hours = Column(Float, nullable=False, default=0.0)
    description = Column(Text, nullable=True)
    entry_date = Column(Date, nullable=False, default=date.today)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    ticket = relationship("Ticket", back_populates="time_entries", lazy="selectin")
    user = relationship("User", back_populates="time_entries", lazy="selectin")