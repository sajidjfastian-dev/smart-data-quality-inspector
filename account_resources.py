"""Account bindings for Streamlit's in-memory upload/media routes.

This small adapter is pinned to Streamlit 1.67's media manager. No session-state
proxy is accessed from an HTTP/download worker.
"""
import hashlib
import threading
import time
from pathlib import Path

_lock = threading.Lock()
_bindings = {}
_public = set()
_deferred_owners = {}


def token_key(token):
    return hashlib.sha256(token.encode()).hexdigest()


def bind(token):
    from streamlit.runtime.scriptrunner import get_script_run_ctx
    context = get_script_run_ctx(suppress_warning=True)
    if context:
        with _lock:
            now = time.time()
            for sid in list(_bindings):
                if _bindings[sid][1] <= now:
                    del _bindings[sid]
            for file_id in list(_deferred_owners):
                sid, expires = _deferred_owners[file_id]
                if expires <= now or (sid == context.session_id and not token):
                    del _deferred_owners[file_id]
            if token:
                _bindings[context.session_id] = (token_key(token), now + 3600)
            else:
                _bindings.pop(context.session_id, None)
        _install_deferred_download_guard()


def _install_deferred_download_guard():
    from streamlit.runtime import get_instance

    manager = get_instance().media_file_mgr
    if getattr(manager, "_dq_deferred_download_guard", False):
        return
    execute_deferred = manager.execute_deferred

    def execute(file_id):
        with manager._lock:
            entry = manager._deferred_callables.get(file_id)
        url = execute_deferred(file_id)
        if entry:
            now = time.time()
            with _lock:
                binding = _bindings.get(entry["session_id"])
                if binding and binding[1] > now:
                    _deferred_owners[media_id(url)] = (entry["session_id"], binding[1])
        return url

    manager.execute_deferred = execute
    manager._dq_deferred_download_guard = True


def allow_public_video(path):
    # Only the checked-in walkthrough is public, never user-supplied paths.
    expected = Path(__file__).parent / "demo_media" / "smart_data_quality_demo.mp4"
    if Path(path).resolve() != expected.resolve():
        raise ValueError("Not a public asset")
    from streamlit.runtime.memory_media_file_storage import _calculate_file_id
    with _lock:
        if not _public:
            _public.add(_calculate_file_id(expected.read_bytes(), "video/mp4"))


def media_id(path):
    return path.rsplit("/", 1)[-1].rsplit(".", 1)[0]


def can_resume(session_id, token):
    if not token:
        return False
    with _lock:
        entry = _bindings.get(session_id)
        return bool(entry and entry[0] == token_key(token) and entry[1] > time.time())


def has_account_binding(session_id):
    with _lock:
        return session_id in _bindings


def is_public(path):
    with _lock:
        return path.startswith("/media/") and media_id(path) in _public


def allowed(path, token):
    from streamlit.runtime import get_instance
    key = token_key(token)
    now = time.time()
    with _lock:
        sessions = {sid for sid, (owner, expires) in _bindings.items() if owner == key and expires > now}
    if path.startswith("/_stcore/upload_file/"):
        return path.split("/")[3] in sessions
    manager = get_instance().media_file_mgr
    with manager._lock:
        resource_id = media_id(path)
        if any(resource_id in manager._files_by_session_and_coord.get(sid, {}).values()
               for sid in sessions):
            return True
    with _lock:
        owner = _deferred_owners.get(resource_id)
        return bool(owner and owner[0] in sessions and owner[1] > now)


