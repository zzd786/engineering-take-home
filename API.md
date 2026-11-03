# API contract: diary sharing

The clinician portal team and the next app release already rely on these endpoints, so please
keep the paths and field names exactly as they are. How you build them is entirely up to you.
Authentication works as in the rest of the API (see the README), and invalid input returns `422`.

## Patient

**`POST /shares`**: share the diary with a doctor.

```json
{"clinician_id": 1, "from_date": "2026-10-01", "to_date": "2026-10-07", "include_notes": false}
```

`from_date` and `to_date` are inclusive calendar dates. `include_notes` is optional and defaults
to `false`. Returns `201` with the share:

```json
{"id": 1, "clinician_id": 1, "from_date": "2026-10-01", "to_date": "2026-10-07",
 "include_notes": false, "created_at": "2026-10-08T09:12:00Z", "revoked_at": null}
```

**`GET /shares`**: the patient's shares, newest first. Returns `200` with a list of shares.

**`POST /shares/{id}/revoke`**: stop sharing. Returns `200` with the share, `revoked_at` set.

**`GET /access-log`**: who read the patient's diary, newest first. Returns `200`:

```json
[{"clinician_id": 1, "clinician_name": "Dr. Lena Hofmann",
  "accessed_at": "2026-10-08T10:03:00Z", "entry_ids": [3, 5]}]
```

### Patient app support

**`GET /sharing-context`**: the authenticated patient's timezone and current consent
wording for the sharing confirmation screen. Returns `200` with `timezone`,
`today` (YYYY-MM-DD in the saved patient timezone), `consent_version`, and `consent_template`. The template uses `{doctor}`, `{from_date}`,
`{to_date}`, `{timezone}`, and `{notes}` placeholders. Notes wording is either
`Notes are included.` or `My notes stay private.`. Missing/invalid auth returns `401`;
clinician accounts receive `403`. This additive endpoint leaves `/me` and `/entries`
unchanged. The server still selects and stores the consent version when creating a share.

**`POST /sharing-preview`**: authenticated patient-only, read-only preview. Accepts the
same selection as POST /shares. Returns `200` with `entry_count`, `note_entry_count`
(entries with nonblank notes), `overlap_count`, and `overlap_includes_notes`.
Counts use the same saved-timezone/legacy date rules as doctor reads. Overlap warnings
consider active permissions for the same doctor, including calendar-day and real-time
intersections across timezone changes; they are conservative, not counts of disclosed entries.
The preview does not create a share or a doctor access record. Missing auth returns `401`,
clinicians receive `403`, and invalid selections/unknown doctors return `422`.
Counts describe current entries, not a fixed export or a reservation. New entries within the
selected dates can also be shared; consent is still checked on every doctor read.

## Clinician

**`GET /clinician/patients/{patient_id}/entries`**: the patient's entries this doctor may see,
newest first. Returns `200`:

```json
[{"id": 3, "recorded_at": "2026-10-02T06:30:00Z", "mood": 4, "symptoms": ["headache"],
  "note": null}]
```

`note` is `null` unless the patient chose to include notes.

## Platform

**`GET /metrics`**: metrics in the Prometheus text format, scraped by the platform team. No
authentication; it is only reachable inside the cluster.

**`POST /telemetry`**: counts a product event sent by the app, e.g. `{"event": "entry_created"}`.
Event names are lowercase letters, digits and underscores, at most 64 characters. Returns `204`.

Valid names beginning with a digit or underscore are accepted. For bounded monitoring labels,
`diary_opened`, `entry_created`, `share_created` and `share_revoked` have dedicated counters;
other valid names are accepted but grouped under `other`. Raw event names are not retained.
See [monitoring instructions](observability/README.md) for product cohort definitions, alerts
and local dashboard access.
