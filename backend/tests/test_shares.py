from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.db import SessionLocal

PATIENT = {"Authorization": "Bearer patient-1"}
OTHER = {"Authorization": "Bearer patient-2"}
CLINICIAN = {"Authorization": "Bearer clinician-1"}
SHARE = {"clinician_id": 1, "from_date": "2026-10-01", "to_date": "2026-10-07"}
SHARE_KEYS = {
    "id",
    "clinician_id",
    "from_date",
    "to_date",
    "include_notes",
    "created_at",
    "revoked_at",
}


def test_create_share_defaults_to_private_notes(client: TestClient) -> None:
    response = client.post("/shares", json=SHARE, headers=PATIENT)
    assert response.status_code == 201
    share = response.json()
    assert set(share) == SHARE_KEYS
    assert share.items() >= SHARE.items()
    assert share["include_notes"] is False
    assert share["revoked_at"] is None
    assert isinstance(share["id"], int)
    assert datetime.fromisoformat(share["created_at"]).utcoffset() is not None


def test_save_consent_evidence_and_timezone(client: TestClient) -> None:
    response = client.post("/shares", json={**SHARE, "include_notes": True}, headers=PATIENT)
    assert response.status_code == 201
    from app.models import DiaryShare, Patient

    with SessionLocal() as db:
        share = db.get(DiaryShare, response.json()["id"])
        assert share.include_notes is True
        assert share.patient_id == 1
        assert share.timezone == "Europe/Berlin"
        assert share.consent_version == "diary-sharing-v1"
        assert "Dr. Lena Hofmann" in share.consent_text
        assert "2026-10-01 through 2026-10-07" in share.consent_text
        assert "Europe/Berlin" in share.consent_text
        assert "Notes are included." in share.consent_text
        assert "revoke" in share.consent_text
        db.get(Patient, 1).timezone = "Europe/Lisbon"
        db.commit()
        db.refresh(share)
        assert share.timezone == "Europe/Berlin"


def test_private_notes_wording(client: TestClient) -> None:
    response = client.post("/shares", json=SHARE, headers=PATIENT)
    assert response.status_code == 201
    from app.models import DiaryShare

    with SessionLocal() as db:
        assert "My notes stay private." in db.get(DiaryShare, response.json()["id"]).consent_text


@pytest.mark.parametrize(
    "changes",
    [
        {"from_date": "2026-10-08"},
        {"from_date": "2026-02-30"},
        {"to_date": "not-a-date"},
        {"clinician_id": 999},
        {"clinician_id": 0},
        {"clinician_id": -1},
        {"include_notes": None},
    ],
)
def test_invalid_share_is_not_saved(client: TestClient, changes: dict) -> None:
    assert client.post("/shares", json={**SHARE, **changes}, headers=PATIENT).status_code == 422
    assert client.get("/shares", headers=PATIENT).json() == []


def test_single_day_and_future_ranges_are_allowed(client: TestClient) -> None:
    payload = {**SHARE, "from_date": "2030-01-01", "to_date": "2030-01-01"}
    assert client.post("/shares", json=payload, headers=PATIENT).status_code == 201


def test_list_is_owned_newest_first_and_includes_revoked(client: TestClient) -> None:
    assert client.get("/shares", headers=PATIENT).json() == []
    ids = []
    for _ in range(3):
        response = client.post("/shares", json=SHARE, headers=PATIENT)
        assert response.status_code == 201
        ids.append(response.json()["id"])
    assert client.post(f"/shares/{ids[0]}/revoke", headers=PATIENT).status_code == 200
    response = client.get("/shares", headers=PATIENT)
    assert response.status_code == 200
    assert [s["id"] for s in response.json()] == ids[::-1]
    assert all(set(s) == SHARE_KEYS for s in response.json())
    assert response.json()[-1]["revoked_at"] is not None
    assert client.get("/shares", headers=OTHER).json() == []


def test_revoke_is_owned_and_repeat_keeps_timestamp(client: TestClient) -> None:
    response = client.post("/shares", json=SHARE, headers=PATIENT)
    assert response.status_code == 201
    share_id = response.json()["id"]
    foreign = client.post(f"/shares/{share_id}/revoke", headers=OTHER)
    missing = client.post("/shares/999/revoke", headers=OTHER)
    assert foreign.status_code == missing.status_code == 404
    assert foreign.json() == missing.json()
    assert client.get("/shares", headers=PATIENT).json()[0]["revoked_at"] is None
    first = client.post(f"/shares/{share_id}/revoke", headers=PATIENT)
    second = client.post(f"/shares/{share_id}/revoke", headers=PATIENT)
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert set(first.json()) == SHARE_KEYS
    assert datetime.fromisoformat(first.json()["revoked_at"]).utcoffset() is not None


@pytest.mark.parametrize(
    "method,path",
    [
        ("post", "/shares"),
        ("get", "/shares"),
        ("post", "/shares/1/revoke"),
    ],
)
def test_share_routes_require_patient(client: TestClient, method: str, path: str) -> None:
    request = getattr(client, method)
    kwargs = {"json": SHARE} if path == "/shares" and method == "post" else {}
    assert request(path, headers=CLINICIAN, **kwargs).status_code == 403
    assert request(path, **kwargs).status_code == 401
    assert (
        request(path, headers={"Authorization": "Bearer patient-999"}, **kwargs).status_code == 401
    )


def test_client_cannot_choose_owner_or_consent_evidence(client: TestClient) -> None:
    payload = {
        **SHARE,
        "patient_id": 2,
        "timezone": "Europe/Lisbon",
        "consent_version": "fake",
        "consent_text": "fake",
        "revoked_at": "2026-01-01T00:00:00Z",
    }
    response = client.post("/shares", json=payload, headers=PATIENT)
    assert response.status_code == 201
    from app.models import DiaryShare

    with SessionLocal() as db:
        share = db.get(DiaryShare, response.json()["id"])
        assert share.patient_id == 1
        assert share.timezone == "Europe/Berlin"
        assert share.consent_version == "diary-sharing-v1"
        assert share.consent_text != "fake"
        assert share.revoked_at is None
    assert client.get("/shares", headers=OTHER).json() == []


def test_creation_time_ties_use_descending_id(client: TestClient) -> None:
    from app.models import DiaryShare

    ids = [client.post("/shares", json=SHARE, headers=PATIENT).json()["id"] for _ in range(2)]
    with SessionLocal() as db:
        timestamp = datetime.fromisoformat("2026-10-08T09:00:00+00:00")
        for share_id in ids:
            db.get(DiaryShare, share_id).created_at = timestamp
        db.commit()
    assert [s["id"] for s in client.get("/shares", headers=PATIENT).json()] == ids[::-1]


def test_legacy_response_shapes_stay_exact(client: TestClient) -> None:
    assert set(client.get("/me", headers=PATIENT).json()) == {"role", "id", "name"}
    entry = {"recorded_at": "2026-10-01T12:00:00Z", "mood": 3}
    response = client.post("/entries", json=entry, headers=PATIENT)
    assert response.status_code == 201
    expected = {"id", "recorded_at", "mood", "symptoms", "note"}
    assert set(response.json()) == expected
    assert set(client.get("/entries", headers=PATIENT).json()[0]) == expected
