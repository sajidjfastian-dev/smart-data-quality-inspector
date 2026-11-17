"""Aggregate-only history repository. No filenames, field labels or cell values.

SSO is deliberately not activated: the deployment's approved identity adapter
and scheduled expiry cleanup must be configured and verified first.
"""

from dataclasses import dataclass, asdict
import hashlib
import json
import os
import re
from uuid import UUID, uuid4

import psycopg
from psycopg.rows import dict_row


class HistoryUnavailable(Exception):
    """Safe message for UI use; never include database or identity details."""


@dataclass(frozen=True)
class InspectionSummary:
    row_count: int
    column_count: int
    finding_count: int
    duplicate_count: int
    health_score: int
    missing_count: int
    email_count: int
    date_count: int
    outlier_count: int
    custom_count: int
    enabled_checks: tuple[str, ...]

    def __post_init__(self):
        for key, value in asdict(self).items():
            if key != "enabled_checks" and (type(value) is not int or value < 0):
                raise ValueError("Invalid summary counts.")
        if self.health_score > 100:
            raise ValueError("Invalid quality score.")
        if not set(self.enabled_checks) <= {"missing", "duplicates", "email", "date", "outliers", "custom"}:
            raise ValueError("Unsupported check name.")


def build_summary(rows, columns, issues, duplicates, health_score, enabled_checks, has_custom_rules=False):
    counts = issues["Issue Type"].value_counts().to_dict()
    checks = set(enabled_checks)
    if has_custom_rules:
        checks.add("custom")
    return InspectionSummary(
        int(rows), int(columns), int(len(issues)), int(duplicates), int(health_score),
        int(counts.get("Missing Value", 0)),
        int(counts.get("Invalid Email", 0)),
        int(counts.get("Invalid Date", 0) + counts.get("Inconsistent Date Format", 0)),
        int(counts.get("Numeric Outlier", 0)),
        int(sum(count for kind, count in counts.items() if str(kind).startswith("Custom:"))),
        tuple(sorted(checks)),
    )


def owner_key_for_verified_identity(issuer, subject):
    """Only call from a server-verified SSO adapter, never a client-supplied ID."""
    if not isinstance(issuer, str) or not issuer or not isinstance(subject, str) or not subject:
        raise ValueError("Verified identity is required.")
    return hashlib.sha256(json.dumps([issuer, subject], ensure_ascii=False).encode()).hexdigest()


def current_history_owner():
    """Fail closed until an approved SSO adapter and retention job are installed.

    Do not substitute browser storage, session-state claims, query parameters,
    arbitrary email addresses or unverified headers for a verified identity.
    """
    return None


def _check_owner(owner):
    if not isinstance(owner, str) or not re.fullmatch(r"[0-9a-f]{64}", owner):
        raise PermissionError("Sign in with your organisation to access history.")


def _connect():
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise HistoryUnavailable("History storage is unavailable. Please try again later.")
    try:
        return psycopg.connect(url, connect_timeout=5, options="-c statement_timeout=5000", row_factory=dict_row)
    except psycopg.Error:
        raise HistoryUnavailable("History storage is unavailable. Please try again later.") from None


class HistoryRepository:
    def __init__(self, connect=None):
        self.connect = connect or _connect

    def save(self, owner, run_key, summary):
        _check_owner(owner)
        run_key = UUID(str(run_key))
        if not isinstance(summary, InspectionSummary):
            raise ValueError("Only inspection summaries can be saved.")
        values = asdict(summary)
        values["enabled_checks"] = list(summary.enabled_checks)
        try:
            with self.connect() as connection:
                connection.execute("DELETE FROM inspection_history WHERE expires_at <= now()")
                result = connection.execute(
                    """INSERT INTO inspection_history (
                        id, owner_key, run_key, row_count, column_count, finding_count,
                        duplicate_count, health_score, missing_count, email_count,
                        date_count, outlier_count, custom_count, enabled_checks
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (owner_key, run_key) DO NOTHING RETURNING id""",
                    (uuid4(), owner, run_key, *values.values()),
                ).fetchone()
                return result is not None
        except psycopg.Error:
            raise HistoryUnavailable("The summary could not be saved. Please try again.") from None

    def list(self, owner, page=0):
        _check_owner(owner)
        if type(page) is not int or page < 0:
            raise ValueError("Invalid history page.")
        try:
            with self.connect() as connection:
                connection.execute("DELETE FROM inspection_history WHERE expires_at <= now()")
                return connection.execute(
                    """SELECT id, created_at, expires_at, row_count, column_count,
                        finding_count, duplicate_count, health_score, missing_count,
                        email_count, date_count, outlier_count, custom_count, enabled_checks
                       FROM inspection_history
                       WHERE owner_key = %s AND expires_at > now()
                       ORDER BY created_at DESC, id DESC LIMIT 51 OFFSET %s""",
                    (owner, page * 50),
                ).fetchall()
        except psycopg.Error:
            raise HistoryUnavailable("History could not be loaded. Please try again.") from None

    def delete(self, owner, record_id):
        _check_owner(owner)
        record_id = UUID(str(record_id))
        try:
            with self.connect() as connection:
                return connection.execute(
                    "DELETE FROM inspection_history WHERE id = %s AND owner_key = %s",
                    (record_id, owner),
                ).rowcount == 1
        except psycopg.Error:
            raise HistoryUnavailable("The summary could not be deleted. Please try again.") from None

    def purge_expired(self):
        """Run from the deployment's scheduled retention job before activation."""
        try:
            with self.connect() as connection:
                return connection.execute(
                    "DELETE FROM inspection_history WHERE expires_at <= now()"
                ).rowcount
        except psycopg.Error:
            raise HistoryUnavailable("Expired history could not be removed.") from None
