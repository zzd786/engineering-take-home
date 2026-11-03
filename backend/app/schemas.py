from datetime import date, datetime

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


# Validates a new diary entry, including its timezone-aware timestamp and mood range.
class EntryIn(BaseModel):
    recorded_at: AwareDatetime
    mood: int = Field(ge=1, le=5)
    symptoms: list[str] = Field(default_factory=list, max_length=20)
    note: str | None = Field(default=None, max_length=2000)


# Keeps diary entry responses limited to the five fields supported by older apps.
class EntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    recorded_at: datetime
    mood: int
    symptoms: list[str]
    note: str | None


# Returns a doctor's ID, name and practice so patients can choose a recipient.
class ClinicianOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    practice: str


# Validates the app event name sent to /telemetry before its counter is increased.
class TelemetryEvent(BaseModel):
    event: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")


# Validates the chosen doctor and date range, with notes excluded unless requested.
class ShareIn(BaseModel):
    clinician_id: int = Field(gt=0)
    from_date: date
    to_date: date
    include_notes: bool = False

    @model_validator(mode="after")
    def check_date_order(self) -> "ShareIn":
        if self.from_date > self.to_date:
            raise ValueError("from_date must not be after to_date")
        return self


# Returns the share's public details and timestamps without internal consent evidence.
class ShareOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    clinician_id: int
    from_date: date
    to_date: date
    include_notes: bool
    created_at: datetime
    revoked_at: datetime | None


# Keeps /me limited to the account role, ID and name expected by older apps.
class Me(BaseModel):
    role: str
    id: int
    name: str
