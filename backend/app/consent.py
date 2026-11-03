"""Versioned consent wording. The sharing UI must show this wording before confirmation."""

from datetime import date

CONSENT_VERSION = "diary-sharing-v1"
CONSENT_TEMPLATE = (
    "I agree to share my mood and symptoms with {doctor} for {from_date} through {to_date}, "
    "inclusive, in {timezone}. {notes} I can revoke access at any time. "
    "I can see who read my diary and when."
)


def consent_wording(
    doctor: str, from_date: date, to_date: date, timezone: str, include_notes: bool
) -> str:
    return CONSENT_TEMPLATE.format(
        doctor=doctor,
        from_date=from_date.isoformat(),
        to_date=to_date.isoformat(),
        timezone=timezone,
        notes="Notes are included." if include_notes else "My notes stay private.",
    )
