from datetime import date, datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


# Stores the patient profile and timezone used when creating diary shares.
class Patient(Base):
    __tablename__ = "patients"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(320), unique=True)
    timezone: Mapped[str] = mapped_column(String(64))  # IANA name, e.g. "Europe/Berlin"
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# Stores the doctor's name and practice for recipient selection and access history.
class Clinician(Base):
    __tablename__ = "clinicians"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    practice: Mapped[str] = mapped_column(String(200))


# Stores one patient's mood, symptoms and private note at a recorded time.
class DiaryEntry(Base):
    __tablename__ = "diary_entries"
    __table_args__ = (CheckConstraint("mood BETWEEN 1 AND 5", name="mood_range"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    mood: Mapped[int]
    symptoms: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    note: Mapped[str | None] = mapped_column(Text)
    # "app-v1" entries were sent without a time zone and stored as if they were UTC.
    source: Mapped[str] = mapped_column(String(16), server_default="app-v2")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# Stores a patient's grant to a doctor: dates, notes permission, wording and revocation time.
class DiaryShare(Base):
    __tablename__ = "diary_shares"
    __table_args__ = (CheckConstraint("from_date <= to_date", name="share_date_order"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    clinician_id: Mapped[int] = mapped_column(ForeignKey("clinicians.id"), index=True)
    from_date: Mapped[date]
    to_date: Mapped[date]
    include_notes: Mapped[bool] = mapped_column(Boolean, server_default="false")
    timezone: Mapped[str] = mapped_column(String(64))
    consent_version: Mapped[str] = mapped_column(String(64))
    consent_text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# Records one doctor read: when it happened, entries and notes returned, and grants used.
class DiaryAccess(Base):
    __tablename__ = "diary_accesses"

    id: Mapped[int] = mapped_column(primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    clinician_id: Mapped[int] = mapped_column(ForeignKey("clinicians.id"))
    accessed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    entry_ids: Mapped[list[int]] = mapped_column(ARRAY(Integer))
    note_entry_ids: Mapped[list[int]] = mapped_column(ARRAY(Integer))
    share_ids: Mapped[list[int]] = mapped_column(ARRAY(Integer))
