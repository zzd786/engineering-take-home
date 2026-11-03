"""Log local alert notifications without patient data or raw request fields."""

import json
from http.server import BaseHTTPRequestHandler, HTTPServer

ALERTS = frozenset(
    {"DiaryAuditWriteFailed", "DiaryDoctorReadErrors", "DiaryDoctorReadSlow", "DiaryApiUnavailable"}
)


def notification(alert):
    labels = alert.get("labels", {})
    name = labels.get("alertname")
    status = alert.get("status")
    if name not in ALERTS or status not in {"firing", "resolved"}:
        return None
    severity = labels.get("severity")
    return {
        "alertname": name,
        "status": status,
        "severity": severity if severity in {"critical", "warning"} else "unknown",
    }


class Receiver(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def respond(self, status):
        self.send_response(status)
        self.end_headers()

    def do_GET(self):
        self.respond(200 if self.path == "/health" else 404)

    def do_POST(self):
        if self.path != "/alerts":
            self.respond(404)
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if size <= 0 or size > 65536:
                self.respond(413)
                return
            payload = json.loads(self.rfile.read(size))
            for alert in payload.get("alerts", []):
                record = notification(alert)
                if record is not None:
                    print(json.dumps({"event": "alert_notification", **record}), flush=True)
            self.respond(200)
        except (ValueError, TypeError, AttributeError):
            self.respond(400)


if __name__ == "__main__":
    HTTPServer(("0.0.0.0", 8080), Receiver).serve_forever()
