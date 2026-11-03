"""Patient-only counts; this neither grants access nor records a doctor disclosure."""

from datetime import UTC, datetime, time
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.access import covers_entry
from app.models import DiaryEntry, DiaryShare


def _bounds(share: DiaryShare) -> tuple[datetime, datetime]:
    zone = ZoneInfo(share.timezone)
    return (
        datetime.combine(share.from_date, time.min, zone).astimezone(UTC),
        datetime.combine(share.to_date, time.max, zone).astimezone(UTC),
    )


def overlaps(first: DiaryShare, second: DiaryShare) -> bool:
    # Warn for either legacy wall-clock dates or modern UTC intervals, including zone changes.
    if first.from_date <= second.to_date and second.from_date <= first.to_date:
        return True
    start, end = _bounds(first)
    other_start, other_end = _bounds(second)
    return start <= other_end and other_start <= end


def preview_diary(db: Session, selection: DiaryShare) -> dict[str, int | bool]:
    entries = db.scalars(select(DiaryEntry).where(DiaryEntry.patient_id == selection.patient_id))
    covered = [entry for entry in entries if covers_entry(selection, entry)]
    grants = db.scalars(
        select(DiaryShare).where(
            DiaryShare.patient_id == selection.patient_id,
            DiaryShare.clinician_id == selection.clinician_id,
            DiaryShare.revoked_at.is_(None),
        )
    )
    overlapping = [grant for grant in grants if overlaps(selection, grant)]
    return {
        "entry_count": len(covered),
        "note_entry_count": sum(bool(entry.note and entry.note.strip()) for entry in covered),
        "overlap_count": len(overlapping),
        "overlap_includes_notes": any(grant.include_notes for grant in overlapping),
    }
