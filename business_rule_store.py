"""Private business-rule definitions, authorized by the live account session."""
import re

from psycopg.types.json import Jsonb
from demo_store import connection, DemoStoreError, DemoConflict


def _owner(conn, token, expected_subject):
    # Lock the session until this transaction finishes: a concurrent revocation
    # cannot race an authorized read or write.
    from account_auth import digest
    if not isinstance(token, str) or not 30 <= len(token) <= 200:
        raise DemoStoreError("Your account session expired. Sign in again.")
    row = conn.execute(
        """SELECT payload FROM dq_auth_records
           WHERE token_hash=%s AND kind='session' AND expires_at>now() FOR SHARE""",
        (digest(token),),
    ).fetchone()
    subject = row["payload"].get("subject") if row and isinstance(row["payload"], dict) else None
    if not isinstance(subject, str) or not subject or subject != expected_subject:
        raise DemoStoreError("Your account session expired. Sign in again.")
    return subject


def _canonical_rules(rules):
    """Store only rule definition fields, never a dataset or unrelated state."""
    from business_rules import validate
    if not isinstance(rules, list) or len(rules) > 500:
        raise ValueError("A maximum of 500 business rules can be saved.")
    result, ids = [], set()
    for rule in rules:
        if not isinstance(rule, dict):
            raise ValueError("The saved business rules are invalid.")
        fields = ("id", "column", "kind", "expected", "mode")
        if any(not isinstance(rule.get(k), str) for k in fields):
            raise ValueError("The saved business rules are invalid.")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", rule["id"]) or rule["id"] in ids:
            raise ValueError("The saved business rules are invalid.")
        ids.add(rule["id"])
        item = {key: rule[key] for key in fields}
        item.update(enabled=True, business=True)
        validate(item)
        result.append(item)
    return result


def load(token, expected_subject):
    with connection() as conn:
        owner = _owner(conn, token, expected_subject)
        row = conn.execute(
            "SELECT rules, version FROM dq_account_business_rules WHERE owner_id=%s", (owner,)
        ).fetchone()
    return (_canonical_rules(row["rules"]), row["version"]) if row else ([], 0)


def save(token, expected_subject, rules, version):
    canonical = _canonical_rules(rules)
    if not isinstance(version, int) or isinstance(version, bool) or version < 0:
        raise ValueError("The saved business rules are invalid.")
    with connection() as conn:
        owner = _owner(conn, token, expected_subject)
        if version == 0:
            row = conn.execute(
                """INSERT INTO dq_account_business_rules(owner_id,rules,version)
                   VALUES (%s,%s,1) ON CONFLICT (owner_id) DO NOTHING RETURNING version""",
                (owner, Jsonb(canonical)),
            ).fetchone()
        else:
            row = conn.execute(
                """UPDATE dq_account_business_rules SET rules=%s,version=version+1,updated_at=now()
                   WHERE owner_id=%s AND version=%s RETURNING version""",
                (Jsonb(canonical), owner, version),
            ).fetchone()
        if not row:
            raise DemoConflict("Your saved rules changed in another session. Reload them before editing.")
    return canonical, row["version"]


def load_into_state(state):
    rules, version = load(state.get("_auth_session"), state.get("auth_subject"))
    state["business_rules"] = rules
    state["_business_rules_version"] = version
