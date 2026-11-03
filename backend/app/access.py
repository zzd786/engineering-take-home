"""Select consented entries and commit read evidence before returning them."""

import logging
from datetime import UTC
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.metrics import AUDIT_FAILURES
from app.models import DiaryAccess, DiaryEntry, DiaryShare
from app.schemas import EntryOut

logger = logging.getLogger("diary.audit")


def covers_entry(share: DiaryShare, entry: DiaryEntry) -> bool:
    # v1 sent wall-clock times mislabeled UTC; another shift would change their day.
    if entry.source == "app-v1":
        day = entry.recorded_at.astimezone(UTC).date()
    else:
        day = entry.recorded_at.astimezone(ZoneInfo(share.timezone)).date()
    return share.from_date <= day <= share.to_date


def read_diary(db: Session, clinician_id: int, patient_id: int) -> list[EntryOut]:
    shares = db.scalars(
        select(DiaryShare)
        .where(
            DiaryShare.patient_id == patient_id,
            DiaryShare.clinician_id == clinician_id,
            DiaryShare.revoked_at.is_(None),
        )
        .order_by(DiaryShare.id)
    ).all()
    if not shares:
        return []

    entries = db.scalars(
        select(DiaryEntry)
        .where(DiaryEntry.patient_id == patient_id)
        .order_by(DiaryEntry.recorded_at.desc(), DiaryEntry.id.desc())
    ).all()
    result = []
    note_ids = []
    used_share_ids = set()
    for entry in entries:
        covering = [share for share in shares if covers_entry(share, entry)]
        if not covering:
            continue
        include_notes = any(share.include_notes for share in covering)
        output = EntryOut.model_validate(entry)
        if not include_notes:
            output.note = None
        elif entry.note is not None:
            note_ids.append(entry.id)
        result.append(output)
        used_share_ids.update(share.id for share in covering)

    # An authorized empty read still records the grants under which it was made.
    evidence = DiaryAccess(
        patient_id=patient_id,
        clinician_id=clinician_id,
        entry_ids=[entry.id for entry in result],
        note_entry_ids=note_ids,
        share_ids=sorted(used_share_ids or {share.id for share in shares}),
    )
    try:
        db.add(evidence)
        db.commit()
    except SQLAlchemyError:
        AUDIT_FAILURES.inc()
        logger.error("audit_write_failed", extra={"error_kind": "database"})
        db.rollback()
        raise HTTPException(503, "Diary access could not be recorded. Try again later.") from None
    return result
