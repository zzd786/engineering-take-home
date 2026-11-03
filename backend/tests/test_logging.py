import json
import logging
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models import DiaryAccess

PATIENT = {"Authorization": "Bearer patient-1"}
DOCTOR = {"Authorization": "Bearer clinician-1"}


def app_records(caplog):
    return [r for r in caplog.records if r.name.startswith("diary.")]


def test_request_ids_are_generated_not_trusted_and_logs_are_safe(client, caplog):
    caplog.set_level(logging.INFO, logger="diary")
    response = client.get(
        "/entries?note=secret-query",
        headers={
            **PATIENT,
            "X-Request-ID": "patient-1-secret-id",
        },
    )
    assert response.status_code == 200
    request_id = response.headers.get("X-Request-ID")
    assert request_id is not None
    UUID(request_id)
    assert request_id != "patient-1-secret-id"
    record = app_records(caplog)[-1]
    assert record.getMessage() == "request_completed"
    assert record.levelno == logging.INFO
    assert record.request_id == request_id
    assert record.route == "/entries"
    assert record.status == 200
    assert record.duration_ms >= 0
    assert client.get("/health").headers["X-Request-ID"] != request_id
    from app.logging_config import JsonFormatter, request_id_context

    output = " ".join(JsonFormatter().format(r) for r in app_records(caplog))
    assert "secret-query" not in output
    assert "patient-1-secret-id" not in output
    assert "Bearer" not in output
    assert request_id_context.get() == "-"


def test_unexpected_errors_log_safe_category_and_request_id(client, caplog, monkeypatch):
    caplog.set_level(logging.INFO, logger="diary")

    def fail(*args, **kwargs):
        raise RuntimeError("secret SQL patient-1 token /private/path")

    monkeypatch.setattr(Session, "scalars", fail)
    response = client.get("/entries", headers=PATIENT)
    assert response.status_code == 500
    record = next(r for r in app_records(caplog) if r.getMessage() == "request_failed")
    assert record.levelno == logging.ERROR
    assert record.error_kind == "unexpected"
    assert record.request_id == response.headers["X-Request-ID"]
    assert record.exc_info is None
    assert "secret SQL" not in caplog.text


def test_audit_failure_has_same_request_id_and_error_level(client, caplog, monkeypatch):
    caplog.set_level(logging.INFO, logger="diary")
    client.post(
        "/shares",
        headers=PATIENT,
        json={
            "clinician_id": 1,
            "from_date": "2026-10-01",
            "to_date": "2026-10-07",
        },
    )
    original = Session.commit

    def fail(session):
        if any(isinstance(row, DiaryAccess) for row in session.new):
            raise SQLAlchemyError("secret SQL")
        return original(session)

    monkeypatch.setattr(Session, "commit", fail)
    response = client.get("/clinician/patients/1/entries", headers=DOCTOR)
    assert response.status_code == 503
    record = next(r for r in app_records(caplog) if r.getMessage() == "audit_write_failed")
    assert record.levelno == logging.ERROR
    assert record.error_kind == "database"
    assert record.request_id == response.headers["X-Request-ID"]
    assert record.exc_info is None


def test_expected_denial_is_not_logged_as_service_error(client, caplog):
    caplog.set_level(logging.INFO, logger="diary")
    response = client.get("/access-log", headers=DOCTOR)
    assert response.status_code == 403
    assert all(r.levelno < logging.WARNING for r in app_records(caplog))


def test_formatter_only_outputs_approved_fields():
    from app.logging_config import JsonFormatter

    record = logging.LogRecord("diary.requests", logging.ERROR, "", 0, "request_failed", (), None)
    record.request_id = "random-correlation-id"
    record.route = "/entries"
    record.status = 500
    record.error_kind = "unexpected"
    record.patient_id = 1
    record.note = "sensitive-marker"
    try:
        raise ValueError("secret traceback")
    except ValueError:
        import sys

        record.exc_info = sys.exc_info()
    output = JsonFormatter().format(record)
    data = json.loads(output)
    assert data["event"] == "request_failed"
    assert data["level"] == "ERROR"
    assert data["request_id"] == "random-correlation-id"
    assert "patient_id" not in data
    assert "note" not in data
    assert "sensitive-marker" not in output
    assert "secret traceback" not in output


def test_log_level_config_supports_levels_and_safe_fallback(monkeypatch):
    from app.logging_config import configured_level

    for name in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
        monkeypatch.setenv("LOG_LEVEL", name.lower())
        assert configured_level() == getattr(logging, name)
    monkeypatch.setenv("LOG_LEVEL", "invalid-sensitive-value")
    assert configured_level() == logging.INFO
