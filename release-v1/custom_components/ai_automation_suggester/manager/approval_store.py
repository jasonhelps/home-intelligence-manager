
import fcntl
import json
import os
import tempfile
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .approval import fingerprint, prepare, APPROVAL_LIFETIME

BASE = Path("/config/.storage/ai_automation_suggester")
STORE = BASE / "approvals.json"

def now():
    return datetime.now(timezone.utc)

@contextmanager
def locked_store():
    lock_path = STORE.with_name(STORE.name + ".lock")
    with open(lock_path, "a+b") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

def load():
    if not STORE.exists():
        return {}
    data = json.loads(STORE.read_text())
    if not isinstance(data, dict):
        raise ValueError("Invalid approval database")
    return data

def save(data):
    fd, name = tempfile.mkstemp(dir=STORE.parent)
    try:
        with os.fdopen(fd, "w") as handle:
            json.dump(data, handle, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, STORE)
    finally:
        if os.path.exists(name):
            os.unlink(name)

def register(automation, services, entities, suggestion_id=None):
    import yaml
    from .validator import validate_complete

    if not isinstance(automation, dict):
        raise PermissionError("Invalid automation")

    validation = validate_complete(
        yaml.safe_dump(automation, sort_keys=False),
        services,
        entities
    )

    if not isinstance(validation, dict):
        raise PermissionError("Validation required")
    if not validation.get("valid"):
        raise PermissionError("Validation failed")
    if validation.get("errors") or validation.get("warnings"):
        raise PermissionError("Unresolved validation findings")

    proposal = prepare(automation)

    record = {
        "approval_id": proposal["proposal_id"],
        "fingerprint": proposal["fingerprint"],
        "created_at": now().isoformat(),
        "expires_at": (
            now() + timedelta(seconds=APPROVAL_LIFETIME)
        ).isoformat(),
        "status": "pending",
        "suggestion_id": suggestion_id,
        "deployment_enabled": False
    }


    with locked_store():
        data = load()
        changed = False

        for existing in data.values():
            if existing.get("status") != "pending":
                continue

            expiry = existing.get("expires_at")
            try:
                expired = not expiry or now() >= datetime.fromisoformat(expiry)
            except (ValueError, TypeError):
                expired = True

            if expired:
                existing["status"] = "expired"
                changed = True
                continue

            if (
                suggestion_id is not None
                and existing.get("suggestion_id") == suggestion_id
                and existing.get("fingerprint") == record["fingerprint"]
            ):
                if changed:
                    save(data)
                return existing

        data[record["approval_id"]] = record
        save(data)

    return record

def transition(approval_id, action, automation=None):
    with locked_store():
        data = load()
        record = data.get(approval_id)

        if not record:
            raise KeyError("Approval not found")

        if record["status"] != "pending":
            raise PermissionError("Approval is not pending")

        if now() >= datetime.fromisoformat(record["expires_at"]):
            record["status"] = "expired"
            save(data)
            raise PermissionError("Approval expired")

        if action == "approve":
            if automation is None:
                raise ValueError("Automation required")
            if fingerprint(automation) != record["fingerprint"]:
                raise PermissionError("Proposal changed")
            record["status"] = "approved"
        elif action == "reject":
            record["status"] = "rejected"
        else:
            raise ValueError("Unsupported action")

        save(data)
        return record

def consume(approval_id, automation):
    with locked_store():
        data = load()
        record = data.get(approval_id)

        if not record or record["status"] != "approved":
            raise PermissionError("Valid approval required")

        if now() >= datetime.fromisoformat(record["expires_at"]):
            record["status"] = "expired"
            save(data)
            raise PermissionError("Approval expired")

        if fingerprint(automation) != record["fingerprint"]:
            raise PermissionError("Proposal changed")

        record["status"] = "consumed"
        save(data)
        return record
