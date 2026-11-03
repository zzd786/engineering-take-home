from datetime import UTC, datetime, timedelta

import pytest
from prometheus_client.parser import text_string_to_metric_families
from sqlalchemy.exc import OperationalError

from app.db import SessionLocal
from app.models import DiaryEntry, DiaryShare

HEADERS = {"Authorization": "Bearer patient-1"}


def values(client):
    body = client.get("/metrics").text
    return {
        sample.name: sample.value
        for family in text_string_to_metric_families(body)
        for sample in family.samples
        if not sample.labels
    }


def test_valid_telemetry_names_have_bounded_labels(client):
    for event in ["0", "_", "123_event", "0" * 64, "private_patient_987", "another_unknown"]:
        assert client.post("/telemetry", headers=HEADERS, json={"event": event}).status_code == 204
    body = client.get("/metrics").text
    assert 'app_events_total{event="other"}' in body
    assert 'event="private_patient_987"' not in body
    assert 'event="another_unknown"' not in body


@pytest.mark.parametrize("followup_days,expected", [(0.5, 0), (1, 1), (7, 1), (8, 0)])
def test_cohorts_use_first_share_and_server_creation_time(client, followup_days, expected):
    now = datetime.now(UTC)
    with SessionLocal() as db:
        for patient, age in [(1, 10), (2, 2)]:
            first = now - timedelta(days=age)
            db.add(
                DiaryShare(
                    patient_id=patient,
                    clinician_id=1,
                    from_date=first.date(),
                    to_date=now.date(),
                    timezone="Europe/Berlin",
                    consent_version="test",
                    consent_text="test",
                    created_at=first,
                    revoked_at=now,
                )
            )
            # recorded_at deliberately differs: product logging uses server created_at.
            db.add(
                DiaryEntry(
                    patient_id=patient,
                    mood=3,
                    recorded_at=now + timedelta(days=10),
                    created_at=first - timedelta(days=1),
                )
            )
        db.add(
            DiaryEntry(
                patient_id=1,
                mood=4,
                recorded_at=now - timedelta(days=100),
                created_at=now - timedelta(days=10 - followup_days),
            )
        )
        db.commit()
    result = values(client)
    assert result["diary_product_metrics_available"] == 1
    assert result["diary_logging_patients"] == 2
    assert result["diary_sharing_patients"] == 2
    assert result["diary_sharing_followup_eligible"] == 1
    assert result["diary_sharing_followup_logged"] == expected


def test_first_ever_entry_after_sharing_is_not_continued_logging(client):
    now = datetime.now(UTC)
    first = now - timedelta(days=10)
    with SessionLocal() as db:
        db.add(
            DiaryShare(
                patient_id=1,
                clinician_id=1,
                from_date=first.date(),
                to_date=now.date(),
                timezone="Europe/Berlin",
                consent_version="test",
                consent_text="test",
                created_at=first,
            )
        )
        db.add(
            DiaryEntry(patient_id=1, mood=3, recorded_at=now, created_at=first + timedelta(days=2))
        )
        db.commit()
    result = values(client)
    assert result["diary_sharing_patients"] == 1
    assert result["diary_sharing_followup_eligible"] == 0
    assert result["diary_sharing_followup_logged"] == 0


def test_unknown_methods_cannot_create_metric_labels_or_log_identifiers(client, caplog):
    client.request("PRIVATEWORD123", "/unknown")
    body = client.get("/metrics").text
    assert 'method="OTHER"' in body
    assert "PRIVATEWORD123" not in body
    assert "PRIVATEWORD123" not in caplog.text


def test_empty_cohort_is_not_a_zero_percent_retention_claim(client):
    result = values(client)
    assert result["diary_sharing_followup_eligible"] == 0
    assert result["diary_sharing_followup_logged"] == 0


def test_product_query_failure_leaves_operational_metrics_available(client, monkeypatch):
    import app.product_metrics as product

    def fail():
        raise OperationalError("private-sql", {}, Exception("private-patient"))

    monkeypatch.setattr(product, "SessionLocal", fail)
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "private-sql" not in response.text
    assert "private-patient" not in response.text
    assert values(client)["diary_product_metrics_available"] == 0
    assert "diary_sharing_followup_eligible" not in values(client)
