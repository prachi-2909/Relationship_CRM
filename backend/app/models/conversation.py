"""Supervisor conversations — short-term memory for /ask.

Not episodic/semantic memory: just the running transcript of one back-and-
forth, persisted so a follow-up question ("what about his stakeholders?")
can be resolved against what was just discussed. Owned by one user; nothing
autonomous reads or acts on it.
"""

import enum
from datetime import datetime

from sqlalchemy import DateTime
from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from .base import Base, TimestampMixin


class MessageRole(str, enum.Enum):
    USER = "user"
    ASSISTANT = "assistant"


_role = SAEnum(MessageRole, native_enum=False, length=16, name="ask_message_role")


class AskConversation(Base, TimestampMixin):
    __tablename__ = "ask_conversations"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)

    messages: Mapped[list["AskMessage"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="AskMessage.id",
    )


class AskMessage(Base, TimestampMixin):
    __tablename__ = "ask_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("ask_conversations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    role: Mapped[MessageRole] = mapped_column(_role, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # only populated for assistant messages
    scope: Mapped[str | None] = mapped_column(String(16), nullable=True)
    generated_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    considered: Mapped[list | None] = mapped_column(JSON, nullable=True)

    conversation: Mapped[AskConversation] = relationship(back_populates="messages")
