# Diary sharing monitoring

## Run

```sh
make observe       # Prometheus, Alertmanager, log-only receiver and Grafana
make test          # application tests, receiver/dashboard tests and alert-rule tests
```

- Sharing dashboard: http://localhost:28003/d/diary-sharing
- API overview: http://localhost:28003/d/api-overview
- Prometheus rules: http://localhost:28002/rules
- Scrape targets: http://localhost:28002/targets
- Notifications: `docker compose logs -f alert-receiver`

Alerts require `make observe`. The receiver logs notifications; it has no inbox or history API.
Published ports bind to loopback. Grafana's anonymous admin access is for a trusted local demo,
not production. No external pager is configured.

## Product signals

| Signal | Calculation |
| --- | --- |
| Sharing adoption | Patients with entries who ever shared / all patients with entries |
| Continued logging | Eligible sharers who created an entry 24–168 hours after first sharing / eligible sharers |

Eligible sharers had an entry at or before first sharing and have at least 168 hours of
follow-up. Use server `created_at`, not a backdated diary date. Count each patient once and
include withdrawn shares. The 24-hour lower bound excludes immediate same-session logging.

Review weekly and read percentages alongside their counts. This measures first-week return,
not whether sharing caused it. The product panels show current database populations;
the dashboard time picker applies to operational charts, not these populations.

A zero denominator displays “No diary users” or “Not enough follow-up”. Queries use -1 as
that display marker, never as a real percentage. Missing source metrics remain missing.
One aggregate query runs per scrape with a two-second SQL statement timeout. Query failure
sets product-query health to 0 and omits counts instead of reporting false zeros.

## Alerts

| Alert | Threshold | Action |
| --- | --- | --- |
| Audit recording failed | Any failure; critical | Check DB connectivity, storage and permissions. Confirm diary disclosure remains blocked. Investigate before restarting. |
| Doctor-read errors | More than 5% 5xx for 5 minutes, with at least 20 requests per rolling 5 minutes; critical | Check API/DB health and safe request-ID logs. |
| Slow doctor reads | p95 above 2 seconds for 10 minutes, with the same volume guard; warning | Check DB latency and API load during clinic hours. |
| API unavailable | Scrape down or missing for 1 minute; critical | Check the API process, dependencies and scrape network. |

A `200 []` doctor response is not an error or proof that a patient exists. Traffic and latency
include authorization and empty responses. Product-query health is a dashboard signal, not
an alert. Low-volume latency estimates are unreliable.

Prometheus scrapes/evaluates every 5 seconds. Alertmanager waits 5 seconds initially, repeats
ongoing notifications hourly and sends resolutions. The audit alert stays active until worker
restart, so it catches failures already present at the first scrape. Restart is not proof of
recovery. A crash before scraping can lose this in-memory signal.

## Check notification delivery manually

Rule tests cover evaluation; backend tests cover blocked disclosure and the failure counter.
To check Alertmanager routing and the receiver without breaking the database, send a synthetic
alert through Alertmanager. This checks delivery, not the full application-to-Prometheus path.

```sh
docker compose exec -T alert-receiver python - <<'PY'
import json
import time
from datetime import UTC, datetime, timedelta
from urllib.request import Request, urlopen

started = datetime.now(UTC) - timedelta(seconds=1)
for state in ("firing", "resolved"):
    now = datetime.now(UTC)
    ends = now + timedelta(minutes=2) if state == "firing" else now
    payload = [{
        "labels": {"alertname": "DiaryAuditWriteFailed", "severity": "critical",
                   "job": "manual-check"},
        "startsAt": started.isoformat(), "endsAt": ends.isoformat(),
    }]
    request = Request("http://alertmanager:9093/api/v2/alerts",
                      data=json.dumps(payload).encode(),
                      headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=5) as response:
        print(state, response.status)
    time.sleep(10)
PY
docker compose logs --since 1m alert-receiver
```

Expect `DiaryAuditWriteFailed` with `firing`, then `resolved`. These two notifications are
from the manual check, not real diary failures. The receiver logs only approved alert names,
states and severities; it discards annotations, URLs, other labels and raw request logs.

## Limits

Production needs an external on-call destination, durable failure reporting, monitoring of the
alert system and authenticated monitoring access. Small product cohorts need privacy/access
controls before wider reporting. Larger datasets need query/index review or cached aggregates.
Local containers and logs do not provide ten-year audit retention.

`/metrics` remains unauthenticated as contracted. Telemetry accepts 1–64 lowercase letters,
digits and underscores, including a leading digit/underscore. Only `diary_opened`,
`entry_created`, `share_created` and `share_revoked` have dedicated labels; other valid names
count as `other`. HTTP methods use a fixed set plus `OTHER`. No patient/doctor IDs or diary
content are exported as labels.
