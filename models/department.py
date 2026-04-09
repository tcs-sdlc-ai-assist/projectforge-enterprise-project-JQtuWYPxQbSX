import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import relationship

from database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Department(Base):
    __tablename__ = "departments"

    id: str = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: str = Column(String(200), unique=True, nullable=False, index=True)
    code: str = Column(String(20), unique=True, nullable=False, index=True)
    description: str | None = Column(Text, nullable=True)
    head_id: str | None = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_at: datetime = Column(DateTime, default=_utcnow, nullable=False)
    updated_at: datetime = Column(DateTime, default=_utcnow, onupdate=_utcnow, nullable=False)

    head = relationship(
        "User",
        foreign_keys=[head_id],
        back_populates="headed_department",
        lazy="selectin",
    )

    members = relationship(
        "User",
        foreign_keys="[User.department_id]",
        back_populates="department",
        lazy="selectin",
    )

    projects = relationship(
        "Project",
        back_populates="department",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<Department(id={self.id!r}, name={self.name!r}, code={self.code!r})>"