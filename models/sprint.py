import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import uuid
from datetime import date, datetime

from sqlalchemy import Column, Date, DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.orm import relationship

from database import Base


class Sprint(Base):
    __tablename__ = "sprints"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    goal = Column(Text, nullable=True)
    status = Column(
        Enum("planning", "active", "completed", name="sprint_status"),
        nullable=False,
        default="planning",
        server_default="planning",
    )
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow, server_default=func.now())

    # Relationships
    project = relationship("Project", back_populates="sprints", lazy="selectin")
    tickets = relationship("Ticket", back_populates="sprint", lazy="selectin")

    def __repr__(self) -> str:
        return f"<Sprint(id={self.id!r}, name={self.name!r}, status={self.status!r})>"