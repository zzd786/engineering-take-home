from datetime import UTC, datetime

from sqlalchemy import func, select

from app.db import SessionLocal
from app.models import DiaryAccess, DiaryEntry, Patient

PATIENT = {"Authorization": "Bearer patient-1"}
BODY = {"clinician_id": 1, "from_date": "2026-10-25", "to_date": "2026-10-25"}


def test_preview_uses_same_local_and_legacy_days_without_disclosure(client):
    with SessionLocal() as db:
        db.add_all(
            [
                DiaryEntry(
                    patient_id=1,
                    recorded_at=datetime(2026, 10, 24, 22, 30, tzinfo=UTC),
                    mood=3,
                    note="private",
                    source="app-v2",
                ),
                DiaryEntry(
                    patient_id=1,
                    recorded_at=datetime(2026, 10, 25, 23, 30, tzinfo=UTC),
                    mood=3,
                    source="app-v2",
                ),
                DiaryEntry(
                    patient_id=1,
                    recorded_at=datetime(2026, 10, 25, 23, 30, tzinfo=UTC),
                    mood=3,
                    source="app-v1",
                ),
                DiaryEntry(
                    patient_id=2,
                    recorded_at=datetime(2026, 10, 25, 12, tzinfo=UTC),
                    mood=3,
                    note="other",
                    source="app-v2",
                ),
            ]
        )
        db.commit()
    response = client.post("/sharing-preview", headers=PATIENT, json=BODY)
    assert response.status_code == 200
    assert response.json() == {
        "entry_count": 2,
        "note_entry_count": 1,
        "overlap_count": 0,
        "overlap_includes_notes": False,
    }
    assert client.get("/shares", headers=PATIENT).json() == []
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(DiaryAccess)) == 0


def test_preview_warns_about_active_overlaps_and_notes_only(client):
    first = client.post("/shares", headers=PATIENT, json={**BODY, "include_notes": True}).json()
    client.post("/shares", headers=PATIENT, json={**BODY, "clinician_id": 2})
    client.post(
        "/shares",
        headers=PATIENT,
        json={**BODY, "from_date": "2026-01-01", "to_date": "2026-01-02"},
    )
    preview = client.post("/sharing-preview", headers=PATIENT, json=BODY).json()
    assert preview["overlap_count"] == 1
    assert preview["overlap_includes_notes"] is True
    client.post(f"/shares/{first['id']}/revoke", headers=PATIENT)
    assert client.post("/sharing-preview", headers=PATIENT, json=BODY).json()["overlap_count"] == 0


def test_overlap_uses_timezone_snapshots_as_well_as_calendar_dates(client):
    with SessionLocal() as db:
        db.get(Patient, 1).timezone = "Pacific/Honolulu"
        db.commit()
    client.post(
        "/shares",
        headers=PATIENT,
        json={
            **BODY,
            "from_date": "2026-10-24",
            "to_date": "2026-10-24",
            "include_notes": True,
        },
    )
    with SessionLocal() as db:
        db.get(Patient, 1).timezone = "Pacific/Kiritimati"
        db.commit()
    # Different calendar dates can cover the same real instants after a timezone change.
    result = client.post("/sharing-preview", headers=PATIENT, json=BODY).json()
    assert result["overlap_count"] == 1
    assert result["overlap_includes_notes"] is True


def test_preview_validates_and_requires_patient(client):
    assert client.post("/sharing-preview", json=BODY).status_code == 401
    assert (
        client.post(
            "/sharing-preview", headers={"Authorization": "Bearer clinician-1"}, json=BODY
        ).status_code
        == 403
    )
    for changes in [{"clinician_id": 999}, {"to_date": "2026-10-01"}, {"from_date": "invalid"}]:
        assert (
            client.post("/sharing-preview", headers=PATIENT, json={**BODY, **changes}).status_code
            == 422
        )


def test_shortcut_today_is_the_saved_timezone_day(client):
    with SessionLocal() as db:
        db.get(Patient, 1).timezone = "Pacific/Kiritimati"
        db.commit()
    from zoneinfo import ZoneInfo

    before = datetime.now(ZoneInfo("Pacific/Kiritimati")).date().isoformat()
    result = client.get("/sharing-context", headers=PATIENT).json()
    after = datetime.now(ZoneInfo("Pacific/Kiritimati")).date().isoformat()
    assert result["today"] in {before, after}
