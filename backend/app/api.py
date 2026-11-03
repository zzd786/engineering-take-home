from collections.abc import Sequence
from datetime import datetime
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.access import read_diary
from app.auth import User, current_clinician, current_patient, current_user
from app.consent import CONSENT_TEMPLATE, CONSENT_VERSION, consent_wording
from app.db import get_db
from app.metrics import APP_EVENTS
from app.models import Clinician, DiaryAccess, DiaryEntry, DiaryShare, Patient
from app.preview import preview_diary
from app.schemas import (
    AccessOut,
    ClinicianOut,
    EntryIn,
    EntryOut,
    Me,
    ShareIn,
    ShareOut,
    TelemetryEvent,
)

router = APIRouter()

Db = Annotated[Session, Depends(get_db)]
AnyUser = Annotated[User, Depends(current_user)]
PatientUser = Annotated[User, Depends(current_patient)]
ClinicianUser = Annotated[User, Depends(current_clinician)]


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/me", response_model=Me)
def me(user: AnyUser) -> User:
    return user


@router.get("/clinicians", response_model=list[ClinicianOut])
def list_clinicians(_: AnyUser, db: Db) -> Sequence[Clinician]:
    return db.scalars(select(Clinician).order_by(Clinician.name)).all()


@router.get("/entries", response_model=list[EntryOut])
def list_entries(user: PatientUser, db: Db) -> Sequence[DiaryEntry]:
    query = (
        select(DiaryEntry)
        .where(DiaryEntry.patient_id == user.id)
        .order_by(DiaryEntry.recorded_at.desc())
    )
    return db.scalars(query).all()


@router.post("/entries", response_model=EntryOut, status_code=201)
def create_entry(body: EntryIn, user: PatientUser, db: Db) -> DiaryEntry:
    entry = DiaryEntry(patient_id=user.id, **body.model_dump())
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@router.get("/sharing-context")
def sharing_context(user: PatientUser, db: Db) -> dict[str, str]:
    patient = db.get(Patient, user.id)
    return {
        "timezone": patient.timezone,
        "today": datetime.now(ZoneInfo(patient.timezone)).date().isoformat(),
        "consent_version": CONSENT_VERSION,
        "consent_template": CONSENT_TEMPLATE,
    }


@router.post("/sharing-preview")
def sharing_preview(body: ShareIn, user: PatientUser, db: Db) -> dict[str, int | bool]:
    if db.get(Clinician, body.clinician_id) is None:
        raise HTTPException(422, "Unknown doctor")
    patient = db.get(Patient, user.id)
    selection = DiaryShare(patient_id=user.id, timezone=patient.timezone, **body.model_dump())
    return preview_diary(db, selection)


@router.post("/shares", response_model=ShareOut, status_code=201)
def create_share(body: ShareIn, user: PatientUser, db: Db) -> DiaryShare:
    clinician = db.get(Clinician, body.clinician_id)
    if clinician is None:
        raise HTTPException(422, "Unknown doctor")
    patient = db.get(Patient, user.id)
    share = DiaryShare(
        patient_id=user.id,
        **body.model_dump(),
        timezone=patient.timezone,
        consent_version=CONSENT_VERSION,
        consent_text=consent_wording(
            clinician.name, body.from_date, body.to_date, patient.timezone, body.include_notes
        ),
    )
    db.add(share)
    db.commit()
    db.refresh(share)
    return share


@router.get("/shares", response_model=list[ShareOut])
def list_shares(user: PatientUser, db: Db) -> Sequence[DiaryShare]:
    return db.scalars(
        select(DiaryShare)
        .where(DiaryShare.patient_id == user.id)
        .order_by(DiaryShare.created_at.desc(), DiaryShare.id.desc())
    ).all()


@router.post("/shares/{share_id}/revoke", response_model=ShareOut)
def revoke_share(share_id: int, user: PatientUser, db: Db) -> DiaryShare:
    # Lock the owned row so simultaneous retries preserve the first withdrawal time.
    share = db.scalar(
        select(DiaryShare)
        .where(DiaryShare.id == share_id, DiaryShare.patient_id == user.id)
        .with_for_update()
    )
    if share is None:
        raise HTTPException(404, "Share not found")
    if share.revoked_at is None:
        share.revoked_at = db.scalar(select(func.clock_timestamp()))
    db.commit()
    db.refresh(share)
    return share


@router.get("/clinician/patients/{patient_id}/entries", response_model=list[EntryOut])
def clinician_entries(patient_id: int, user: ClinicianUser, db: Db) -> list[EntryOut]:
    return read_diary(db, user.id, patient_id)


@router.get("/access-log", response_model=list[AccessOut])
def access_log(user: PatientUser, db: Db) -> list[AccessOut]:
    rows = db.execute(
        select(DiaryAccess, Clinician.name)
        .join(Clinician, Clinician.id == DiaryAccess.clinician_id)
        .where(DiaryAccess.patient_id == user.id)
        .order_by(DiaryAccess.accessed_at.desc(), DiaryAccess.id.desc())
    ).all()
    return [
        AccessOut(
            clinician_id=record.clinician_id,
            clinician_name=name,
            accessed_at=record.accessed_at,
            entry_ids=record.entry_ids,
        )
        for record, name in rows
    ]


@router.post("/telemetry", status_code=204)
def telemetry(body: TelemetryEvent, _: AnyUser) -> Response:
    APP_EVENTS.labels(body.event).inc()
    return Response(status_code=204)
