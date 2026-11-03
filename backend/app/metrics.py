"""Prometheus metrics, served on /metrics and scraped by the platform team."""

from prometheus_client import Counter, Histogram

REQUESTS = Counter(
    "http_requests_total",
    "HTTP requests by route template and status.",
    ["method", "route", "status"],
)
AUDIT_FAILURES = Counter("diary_audit_write_failures_total", "Failed diary access record writes.")
KNOWN_EVENTS = frozenset({"diary_opened", "entry_created", "share_created", "share_revoked"})
APP_EVENTS = Counter("app_events_total", "Product events sent by the app.", ["event"])
LATENCY = Histogram(
    "http_request_duration_seconds", "HTTP request duration by route template.", ["method", "route"]
)
