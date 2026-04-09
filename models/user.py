import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    username: Mapped[str] = mapped_column(
        String(150),
        unique=True,
        nullable=False,
        index=True,
    )
    hashed_password: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    email: Mapped[str | None] = mapped_column(
        String(255),
        unique=True,
        nullable=True,
        index=True,
    )
    full_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    role: Mapped[str] = mapped_column(
        Enum(
            "super_admin",
            "project_manager",
            "team_lead",
            "developer",
            "qa_tester",
            "viewer",
            name="user_role_enum",
        ),
        nullable=False,
        default="viewer",
    )
    department_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("departments.id", ondelete="SET NULL"),
        nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    department: Mapped["Department"] = relationship(
        "Department",
        back_populates="members",
        lazy="selectin",
    )

    project_memberships: Mapped[list["ProjectMember"]] = relationship(
        "ProjectMember",
        back_populates="user",
        lazy="selectin",
        cascade="all, delete-orphan",
    )

    owned_projects: Mapped[list["Project"]] = relationship(
        "Project",
        back_populates="owner",
        lazy="selectin",
        foreign_keys="[Project.owner_id]",
    )

    assigned_tickets: Mapped[list["Ticket"]] = relationship(
        "Ticket",
        back_populates="assignee",
        lazy="selectin",
        foreign_keys="[Ticket.assignee_id]",
    )

    reported_tickets: Mapped[list["Ticket"]] = relationship(
        "Ticket",
        back_populates="reporter",
        lazy="selectin",
        foreign_keys="[Ticket.reporter_id]",
    )

    comments: Mapped[list["Comment"]] = relationship(
        "Comment",
        back_populates="user",
        lazy="selectin",
        cascade="all, delete-orphan",
    )

    time_entries: Mapped[list["TimeEntry"]] = relationship(
        "TimeEntry",
        back_populates="user",
        lazy="selectin",
        cascade="all, delete-orphan",
    )

    audit_logs: Mapped[list["AuditLog"]] = relationship(
        "AuditLog",
        back_populates="user",
        lazy="selectin",
        cascade="all, delete-orphan",
    )

    headed_department: Mapped["Department"] = relationship(
        "Department",
        back_populates="head",
        lazy="selectin",
        foreign_keys="[Department.head_id]",
        uselist=False,
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id!r}, username={self.username!r}, role={self.role!r})>"