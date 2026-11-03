from datetime import datetime

import pytest
from prometheus_client.parser import text_string_to_metric_families
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import DiaryAccess, DiaryEntry

PATIENT = {"Authorization": "Bearer patient-1"}
OTHER = {"Authorization": "Bearer patient-2"}
DOCTOR = {"Authorization": "Bearer clinician-1"}
DOCTOR_2 = {"Authorization": "Bearer clinician-2"}
PATH = "/clinician/patients/1/entries"


def grant(client, start="2026-10-01", end="2026-10-07", notes=False, headers=PATIENT):
    response = client.post(
        "/shares",
        headers=headers,
        json={
            "clinician_id": 1,
            "from_date": start,
            "to_date": end,
            "include_notes": notes,
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def entry(at, patient=1, source="app-v2"):
    with SessionLocal() as db:
        row = DiaryEntry(
            patient_id=patient,
            recorded_at=datetime.fromisoformat(at),
            mood=4,
            symptoms=["headache"],
            note="private-note-marker",
            source=source,
        )
        db.add(row)
        db.commit()
        return row.id


def test_no_grant_and_missing_patient_are_indistinguishable(client):
    a = client.get(PATH, headers=DOCTOR)
    b = client.get("/clinician/patients/999/entries", headers=DOCTOR)
    assert a.status_code == b.status_code == 200
    assert a.json() == b.json() == []
    assert client.get("/access-log", headers=PATIENT).json() == []


def test_overlaps_notes_revocation_and_patient_isolation(client):
    first = entry("2026-10-02T12:00:00+00:00")
    second = entry("2026-10-06T12:00:00+00:00")
    entry("2026-10-06T12:00:00+00:00", patient=2)
    plain = grant(client)
    notes = grant(client, "2026-10-05", "2026-10-07", True)
    result = client.get(PATH, headers=DOCTOR)
    assert result.status_code == 200
    assert [e["id"] for e in result.json()] == [second, first]
    assert set(result.json()[0]) == {"id", "recorded_at", "mood", "symptoms", "note"}
    assert result.json()[0]["note"] == "private-note-marker"
    assert result.json()[1]["note"] is None
    assert client.get(PATH, headers=DOCTOR_2).json() == []
    client.post(f"/shares/{notes}/revoke", headers=PATIENT)
    assert all(e["note"] is None for e in client.get(PATH, headers=DOCTOR).json())
    client.post(f"/shares/{plain}/revoke", headers=PATIENT)
    assert client.get(PATH, headers=DOCTOR).json() == []
    history = client.get("/access-log", headers=PATIENT).json()
    assert len(history) == 2
    assert history[0]["entry_ids"] == [second, first]
    assert history[0]["accessed_at"] >= history[1]["accessed_at"]
    assert set(history[0]) == {"clinician_id", "clinician_name", "accessed_at", "entry_ids"}
    assert history[0]["clinician_name"] == "Dr. Lena Hofmann"
    assert history[0]["clinician_id"] == 1
    assert client.get("/access-log", headers=OTHER).json() == []
    with SessionLocal() as db:
        rows = db.scalars(select(DiaryAccess).order_by(DiaryAccess.id)).all()
        assert rows[0].note_entry_ids == [second]
        assert set(rows[0].share_ids) == {plain, notes}
        assert rows[1].note_entry_ids == []


@pytest.mark.parametrize(
    "day,start,end",
    [
        ("2026-03-29", "2026-03-28T23:00:00+00:00", "2026-03-29T22:00:00+00:00"),
        ("2026-10-25", "2026-10-24T22:00:00+00:00", "2026-10-25T23:00:00+00:00"),
    ],
)
def test_inclusive_local_day_across_dst(client, day, start, end):
    from datetime import timedelta

    before = (datetime.fromisoformat(start) - timedelta(microseconds=1)).isoformat()
    last = (datetime.fromisoformat(end) - timedelta(microseconds=1)).isoformat()
    entry(before)
    first_id = entry(start)
    last_id = entry(last)
    entry(end)
    grant(client, day, day)
    result = client.get(PATH, headers=DOCTOR).json()
    assert [e["id"] for e in result] == [last_id, first_id]


def test_legacy_wall_date_is_not_shifted_and_timestamp_is_unchanged(client):
    legacy = entry("2026-03-14T23:50:00+00:00", source="app-v1")
    entry("2026-03-14T23:50:00+00:00")  # March 15 in Berlin, not covered.
    grant(client, "2026-03-14", "2026-03-14")
    result = client.get(PATH, headers=DOCTOR).json()
    assert [e["id"] for e in result] == [legacy]
    assert result[0]["recorded_at"] == "2026-03-14T23:50:00Z"


def test_empty_authorized_read_is_recorded(client):
    grant(client)
    assert client.get(PATH, headers=DOCTOR).json() == []
    history = client.get("/access-log", headers=PATIENT)
    assert history.status_code == 200
    assert len(history.json()) == 1
    assert history.json()[0]["entry_ids"] == []


def test_each_read_is_recorded_before_response(client):
    grant(client)
    entry_id = entry("2026-10-02T12:00:00+00:00")
    for _ in range(2):
        assert client.get(PATH, headers=DOCTOR).status_code == 200
    with SessionLocal() as db:
        rows = db.scalars(select(DiaryAccess)).all()
        assert len(rows) == 2
        assert all(r.patient_id == 1 and r.clinician_id == 1 for r in rows)
        assert all(r.entry_ids == [entry_id] for r in rows)
        assert all(r.accessed_at.utcoffset() is not None for r in rows)


def test_audit_commit_failure_blocks_data_and_signals(client, monkeypatch, caplog):
    grant(client)
    entry("2026-10-02T12:00:00+00:00")

    def failure_count():
        for family in text_string_to_metric_families(client.get("/metrics").text):
            for sample in family.samples:
                if sample.name == "diary_audit_write_failures_total":
                    assert sample.labels == {}
                    return sample.value
        pytest.fail("Audit failure metric missing")

    before = failure_count()
    original = Session.commit

    def fail_audit(session):
        if any(isinstance(row, DiaryAccess) for row in session.new):
            raise SQLAlchemyError("secret SQL private-note-marker")
        return original(session)

    monkeypatch.setattr(Session, "commit", fail_audit)
    result = client.get(PATH, headers=DOCTOR)
    assert result.status_code == 503
    assert result.json() == {"detail": "Diary access could not be recorded. Try again later."}
    assert "private-note-marker" not in result.text
    assert client.get("/access-log", headers=PATIENT).json() == []
    assert failure_count() == before + 1
    assert "secret SQL" not in caplog.text


@pytest.mark.parametrize(
    "path,headers,code",
    [
        (PATH, PATIENT, 403),
        (PATH, {}, 401),
        ("/access-log", DOCTOR, 403),
        ("/access-log", {}, 401),
    ],
)
def test_roles(client, path, headers, code):
    assert client.get(path, headers=headers).status_code == code


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE diary_accesses SET entry_ids = '{}'",
        "DELETE FROM diary_accesses",
    ],
)
def test_access_records_reject_update_and_delete(client, statement):
    grant(client)
    assert client.get(PATH, headers=DOCTOR).status_code == 200
    with SessionLocal() as db:
        assert db.scalar(select(DiaryAccess.id)) is not None
        with pytest.raises(DBAPIError):
            db.execute(text(statement))
        db.rollback()
    assert len(client.get("/access-log", headers=PATIENT).json()) == 1


def test_logs_do_not_contain_bodies_or_raw_paths(client, caplog):
    import logging

    caplog.set_level(logging.INFO, logger="diary.requests")
    client.post(
        "/entries",
        headers=PATIENT,
        json={
            "recorded_at": "2026-10-02T12:00:00Z",
            "mood": 4,
            "note": "sensitive-marker",
        },
    )
    client.get("/clinician/patients/987654/entries", headers=DOCTOR)
    messages = " ".join(r.getMessage() for r in caplog.records if r.name == "diary.requests")
    assert "sensitive-marker" not in messages
    assert "987654" not in messages
    assert any(
        getattr(r, "route", None) == "/clinician/patients/{patient_id}/entries"
        for r in caplog.records
        if r.name == "diary.requests"
    )


def test_unexpected_error_is_generic_and_does_not_log_details(client, monkeypatch, caplog):
    def broken(*args, **kwargs):
        raise RuntimeError("secret SQL /private/path private-note-marker")

    monkeypatch.setattr(Session, "scalars", broken)
    response = client.get("/entries", headers=PATIENT)
    assert response.status_code == 500
    assert response.json() == {"detail": "An unexpected error occurred."}
    assert "secret SQL" not in caplog.text


def test_timezone_snapshot_survives_profile_change(client):
    from app.models import Patient

    grant(client, "2026-10-01", "2026-10-01")
    entry_id = entry("2026-09-30T22:30:00+00:00")  # Oct 1 Berlin, Sep 30 Lisbon.
    with SessionLocal() as db:
        db.get(Patient, 1).timezone = "Europe/Lisbon"
        db.commit()
    response = client.get(PATH, headers=DOCTOR)
    assert response.status_code == 200
    assert [e["id"] for e in response.json()] == [entry_id]


def test_legacy_nonexistent_dst_wall_time_keeps_calendar_day(client):
    entry_id = entry("2026-03-29T02:30:00+00:00", source="app-v1")
    grant(client, "2026-03-29", "2026-03-29")
    response = client.get(PATH, headers=DOCTOR)
    assert response.status_code == 200
    assert [e["id"] for e in response.json()] == [entry_id]


def test_validation_does_not_echo_sensitive_input(client):
    response = client.post(
        "/entries",
        headers=PATIENT,
        json={
            "recorded_at": "bad-sensitive-marker",
            "mood": 99,
        },
    )
    assert response.status_code == 422
    assert "bad-sensitive-marker" not in response.text
