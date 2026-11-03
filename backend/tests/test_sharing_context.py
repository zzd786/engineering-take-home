from app.consent import CONSENT_TEMPLATE, CONSENT_VERSION


def test_sharing_context_is_patient_only_and_preserves_old_profile(client):
    response = client.get("/sharing-context", headers={"Authorization": "Bearer patient-1"})
    assert response.status_code == 200
    payload = response.json()
    from datetime import date
    assert date.fromisoformat(payload.pop("today"))
    assert payload == {
        "timezone": "Europe/Berlin",
        "consent_version": CONSENT_VERSION,
        "consent_template": CONSENT_TEMPLATE,
    }
    assert client.get("/sharing-context").status_code == 401
    assert (
        client.get("/sharing-context", headers={"Authorization": "Bearer clinician-1"}).status_code
        == 403
    )
    assert set(client.get("/me", headers={"Authorization": "Bearer patient-1"}).json()) == {
        "role",
        "id",
        "name",
    }
