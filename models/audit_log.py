import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.orm import relationship

from database import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    entity_type = Column(String(100), nullable=False, index=True)
    entity_id = Column(String(36), nullable=False, index=True)
    action = Column(
        Enum("create", "update", "delete", name="audit_action_enum"),
        nullable=False,
        index=True,
    )
    user_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    details = Column(Text, nullable=True)
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)

    user = relationship("User", back_populates="audit_logs", lazy="selectin")

    def __repr__(self) -> str:
        return (
            f"<AuditLog(id={self.id!r}, action={self.action!r}, "
            f"entity_type={self.entity_type!r}, entity_id={self.entity_id!r})>"
        )