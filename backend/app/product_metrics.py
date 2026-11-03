"""Identifier-free product aggregates, calculated from persisted server timestamps."""

import logging

from prometheus_client.core import GaugeMetricFamily
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.db import SessionLocal

QUERY = text("""
WITH logging AS (SELECT DISTINCT patient_id FROM diary_entries),
first_shares AS (
    SELECT s.patient_id, min(s.created_at) AS first_at
    FROM diary_shares s JOIN logging l ON l.patient_id = s.patient_id
    GROUP BY s.patient_id
), mature AS (
    SELECT * FROM first_shares f WHERE first_at <= now() - interval '168 hours'
    AND EXISTS (
        SELECT 1 FROM diary_entries e
        WHERE e.patient_id = f.patient_id AND e.created_at <= f.first_at
    )
)
SELECT
    (SELECT count(*) FROM logging) AS logging_patients,
    (SELECT count(*) FROM first_shares) AS sharing_patients,
    (SELECT count(*) FROM mature) AS sharing_followup_eligible,
    (SELECT count(*) FROM mature m WHERE EXISTS (
        SELECT 1 FROM diary_entries e WHERE e.patient_id = m.patient_id
        AND e.created_at >= m.first_at + interval '24 hours'
        AND e.created_at <= m.first_at + interval '168 hours'
    )) AS sharing_followup_logged
""")
DESCRIPTIONS = {
    "logging_patients": "Patients with at least one stored diary entry; adoption denominator.",
    "sharing_patients": "Diary users who ever created a share, including withdrawn shares.",
    "sharing_followup_eligible": "Prior diary users whose first share is at least seven days old.",
    "sharing_followup_logged": "Eligible sharers logging 24-168 hours after first share.",
}


class ProductCollector:
    def describe(self):
        yield GaugeMetricFamily("diary_product_metrics_available", "Product query succeeded.")
        for name, description in DESCRIPTIONS.items():
            yield GaugeMetricFamily(f"diary_{name}", description)

    def collect(self):
        try:
            with SessionLocal() as db:
                db.execute(text("SET LOCAL statement_timeout = '2000ms'"))
                values = db.execute(QUERY).mappings().one()
        except SQLAlchemyError:
            logging.getLogger("diary.metrics").error(
                "product_metrics_unavailable", extra={"error_kind": "database"}
            )
            yield GaugeMetricFamily(
                "diary_product_metrics_available", "Product query succeeded.", value=0
            )
            return
        yield GaugeMetricFamily(
            "diary_product_metrics_available", "Product query succeeded.", value=1
        )
        for name, description in DESCRIPTIONS.items():
            yield GaugeMetricFamily(f"diary_{name}", description, value=values[name])
