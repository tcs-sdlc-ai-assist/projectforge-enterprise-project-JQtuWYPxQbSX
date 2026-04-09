import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import relationship

from database import Base


class Comment(Base):
    __tablename__ = "comments"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    ticket_id = Column(String(36), ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False, index=True)
    author_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    parent_id = Column(String(36), ForeignKey("comments.id", ondelete="CASCADE"), nullable=True, index=True)
    content = Column(Text, nullable=False)
    is_internal = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    ticket = relationship("Ticket", back_populates="comments", lazy="selectin")
    author = relationship("User", back_populates="comments", lazy="selectin")
    parent = relationship(
        "Comment",
        back_populates="replies",
        remote_side=[id],
        lazy="selectin",
    )
    replies = relationship(
        "Comment",
        back_populates="parent",
        lazy="selectin",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Comment(id={self.id!r}, ticket_id={self.ticket_id!r}, author_id={self.author_id!r})>"