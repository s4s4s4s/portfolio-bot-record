"""SQLAlchemy 2.x модели. Все datetime в UTC.

Пояснения:
  • `Slot` — слоты с end_at; multi-service на одно время у мастера.
  • `Booking.slot_id` — UNIQUE: один слот = максимум одна активная бронь.
  • `Client.tg_user_id` — natural unique key; `id` нужен для FK.
  • `UserUsage` — дневной лимит сообщений и блокировки.
  • `AdminLog` — audit trail админ-действий.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Service(Base):
    __tablename__ = "services"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    duration_min: Mapped[int] = mapped_column(Integer, nullable=False)
    price_kop: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    def __repr__(self) -> str:
        return f"<Service id={self.id} name={self.name!r} duration={self.duration_min}m>"


class Master(Base):
    __tablename__ = "masters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    services_csv: Mapped[str] = mapped_column(String(120), nullable=False)
    schedule_json: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    def __repr__(self) -> str:
        return f"<Master id={self.id} name={self.name!r}>"


class Client(Base):
    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tg_user_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    tg_username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    phone: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), server_default=func.now(), nullable=False,
    )

    bookings: Mapped[list[Booking]] = relationship(back_populates="client")

    def __repr__(self) -> str:
        return f"<Client id={self.id} tg_user_id={self.tg_user_id} phone={self.phone}>"


class UserUsage(Base):
    """Счётчик входящих действий и strikes за превышение дневного лимита."""

    __tablename__ = "user_usage"

    tg_user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    day_key: Mapped[str] = mapped_column(String(10), nullable=False)
    msg_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    strike_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_violation_day: Mapped[str | None] = mapped_column(String(10), nullable=True)
    blocked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    blocked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)

    def __repr__(self) -> str:
        return (
            f"<UserUsage tg={self.tg_user_id} day={self.day_key} "
            f"count={self.msg_count} strikes={self.strike_count} blocked={self.blocked}>"
        )


class Slot(Base):
    __tablename__ = "slots"
    __table_args__ = (
        Index("ix_slot_start_at", "start_at"),
        Index("ix_slot_status", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    master_id: Mapped[int] = mapped_column(ForeignKey("masters.id"), nullable=False)
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id"), nullable=False)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="available", nullable=False)
    booking_id: Mapped[int | None] = mapped_column(
        ForeignKey("bookings.id", use_alter=True, name="fk_slot_booking"),
        nullable=True,
    )

    master: Mapped[Master] = relationship(foreign_keys=[master_id])
    service: Mapped[Service] = relationship(foreign_keys=[service_id])

    def __repr__(self) -> str:
        return f"<Slot id={self.id} master_id={self.master_id} start={self.start_at} status={self.status}>"


class Booking(Base):
    __tablename__ = "bookings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slot_id: Mapped[int] = mapped_column(
        ForeignKey("slots.id"), unique=True, nullable=False,
    )
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), server_default=func.now(), nullable=False,
    )
    reminded_24h: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    reminded_2h: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    cancel_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)

    slot: Mapped[Slot] = relationship(foreign_keys=[slot_id])
    client: Mapped[Client] = relationship(back_populates="bookings", foreign_keys=[client_id])

    def __repr__(self) -> str:
        return f"<Booking id={self.id} slot_id={self.slot_id} client_id={self.client_id} status={self.status}>"


class AdminLog(Base):
    __tablename__ = "admin_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    admin_tg_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    payload_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), server_default=func.now(), nullable=False,
    )

    def __repr__(self) -> str:
        return f"<AdminLog id={self.id} admin_tg_id={self.admin_tg_id} action={self.action}>"
