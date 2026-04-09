import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, String, Table, UniqueConstraint
from sqlalchemy.orm import relationship

from database import Base

ticket_labels = Table(
    "ticket_labels",
    Base.metadata,
    Column("ticket_id", String(36), ForeignKey("tickets.id", ondelete="CASCADE"), primary_key=True),
    Column("label_id", String(36), ForeignKey("labels.id", ondelete="CASCADE"), primary_key=True),
)


class Label(Base):
    __tablename__ = "labels"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(100), nullable=False)
    color = Column(String(7), nullable=False, default="#6366f1")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("project_id", "name", name="uq_label_project_name"),
    )

    project = relationship("Project", back_populates="labels", lazy="selectin")
    tickets = relationship(
        "Ticket",
        secondary=ticket_labels,
        back_populates="labels",
        lazy="selectin",
    )