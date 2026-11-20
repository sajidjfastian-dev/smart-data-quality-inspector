"""Request ownership is an immutable authenticated subject, not a display name."""

class _SeedCapability:
    def __deepcopy__(self, memo):
        return self

    def __reduce__(self):
        raise TypeError("Offline seed authorization must not be serialized")


_SEED_CAPABILITY = _SeedCapability()
_LOCAL_DEMO_CAPABILITY = object()


def sample_seed_state(name):
    """Offline public-catalog construction only; this capability is never serializable."""
    return {"demo_user": name, "demo_role": "Submitter", "_seed_capability": _SEED_CAPABILITY}


def is_seed(state):
    return state.get("_seed_capability") is _SEED_CAPABILITY


def is_local_demo(state):
    return state.get("_local_demo_capability") is _LOCAL_DEMO_CAPABILITY


def owns(state, record):
    if not record:
        return False
    if state.get("auth_subject"):
        return record.get("owner_id") == state["auth_subject"]
    return is_seed(state) and not record.get("owner_id") and record.get("submitted_by") == state.get("demo_user")


def public_example(record):
    from public_sample import SOURCE_ID
    session = record.get("session_id", "")
    return bool(not record.get("owner_id") and record.get("synthetic")
                and record.get("source_id")
                and (session.startswith("DEMO-HISTORY-")
                     or (record.get("source_id") == SOURCE_ID and session.startswith(SOURCE_ID.upper() + "-"))))


def auth_state(state):
    return {key: state[key] for key in ("auth_subject", "_auth_session", "_seed_capability") if key in state}
