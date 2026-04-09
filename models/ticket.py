import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import uuid
from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    String,
    Table,
    Text,
)
from sqlalchemy.orm import relationship

from database import Base


ticket_labels = Table(
    "ticket_labels",
    Base.metadata,
    Column("ticket_id", String(36), ForeignKey("tickets.id", ondelete="CASCADE"), primary_key=True),
    Column("label_id", String(36), ForeignKey("labels.id", ondelete="CASCADE"), primary_key=True),
)


class Ticket(Base):
    __tablename__ = "tickets"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    sprint_id = Column(String(36), ForeignKey("sprints.id", ondelete="SET NULL"), nullable=True)
    parent_id = Column(String(36), ForeignKey("tickets.id", ondelete="SET NULL"), nullable=True)
    key = Column(String(50), nullable=True, index=True)
    title = Column(String(300), nullable=False)
    description = Column(Text, nullable=True)
    type = Column(
        Enum("feature", "bug", "task", "improvement", name="ticket_type_enum"),
        nullable=False,
        default="task",
    )
    status = Column(
        Enum("backlog", "todo", "in_progress", "in_review", "done", "closed", name="ticket_status_enum"),
        nullable=False,
        default="backlog",
    )
    priority = Column(
        Enum("critical", "high", "medium", "low", name="ticket_priority_enum"),
        nullable=False,
        default="medium",
    )
    assignee_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reporter_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    estimated_hours = Column(Float, nullable=True)
    story_points = Column(Float, nullable=True)
    due_date = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    project = relationship("Project", back_populates="tickets", lazy="selectin")
    sprint = relationship("Sprint", back_populates="tickets", lazy="selectin")
    assignee = relationship(
        "User",
        foreign_keys=[assignee_id],
        back_populates="assigned_tickets",
        lazy="selectin",
    )
    reporter = relationship(
        "User",
        foreign_keys=[reporter_id],
        back_populates="reported_tickets",
        lazy="selectin",
    )
    parent = relationship(
        "Ticket",
        remote_side=[id],
        back_populates="subtasks",
        lazy="selectin",
    )
    subtasks = relationship(
        "Ticket",
        back_populates="parent",
        lazy="selectin",
    )
    labels = relationship(
        "Label",
        secondary=ticket_labels,
        back_populates="tickets",
        lazy="selectin",
    )
    comments = relationship(
        "Comment",
        back_populates="ticket",
        lazy="selectin",
        cascade="all, delete-orphan",
    )
    time_entries = relationship(
        "TimeEntry",
        back_populates="ticket",
        lazy="selectin",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Ticket(id={self.id}, key={self.key}, title={self.title!r}, status={self.status})>"