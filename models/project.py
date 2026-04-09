import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base

if TYPE_CHECKING:
    from models.label import Label
    from models.project_member import ProjectMember
    from models.sprint import Sprint
    from models.ticket import Ticket
    from models.user import User


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    key: Mapped[Optional[str]] = mapped_column(
        String(20),
        unique=True,
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        Enum(
            "planning",
            "active",
            "on_hold",
            "completed",
            "archived",
            name="project_status",
        ),
        nullable=False,
        default="planning",
    )
    owner_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    department_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("departments.id", ondelete="SET NULL"),
        nullable=True,
    )
    start_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )
    end_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    owner: Mapped[Optional["User"]] = relationship(
        "User",
        back_populates="owned_projects",
        foreign_keys=[owner_id],
        lazy="selectin",
    )
    department: Mapped[Optional["Department"]] = relationship(
        "Department",
        back_populates="projects",
        lazy="selectin",
    )
    members: Mapped[List["ProjectMember"]] = relationship(
        "ProjectMember",
        back_populates="project",
        lazy="selectin",
        cascade="all, delete-orphan",
    )
    sprints: Mapped[List["Sprint"]] = relationship(
        "Sprint",
        back_populates="project",
        lazy="selectin",
        cascade="all, delete-orphan",
    )
    tickets: Mapped[List["Ticket"]] = relationship(
        "Ticket",
        back_populates="project",
        lazy="selectin",
        cascade="all, delete-orphan",
    )
    labels: Mapped[List["Label"]] = relationship(
        "Label",
        back_populates="project",
        lazy="selectin",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Project(id={self.id!r}, key={self.key!r}, name={self.name!r}, status={self.status!r})>"


# Avoid circular import at module level; use string reference for Department
from models.department import Department  # noqa: E402, F401