
"""Safe deployment planning. No live writes."""
import hashlib
import json
from pathlib import Path

def checksum(data):
    return hashlib.sha256(data).hexdigest()

def build_plan(original, proposed):
    if not isinstance(original, dict) or not isinstance(proposed, dict):
        raise ValueError("Automation configurations must be dictionaries")

    before = json.dumps(original, sort_keys=True).encode()
    after = json.dumps(proposed, sort_keys=True).encode()

    return {
        "original_checksum": checksum(before),
        "proposed_checksum": checksum(after),
        "changed": before != after,
        "approval_required": True,
        "deployment_enabled": False,
        "ready_to_apply": False,
    }

def prepare_backup(source, destination):
    """Back up an explicitly supplied file without modifying it."""
    source = Path(source)
    destination = Path(destination)

    if not source.is_file():
        raise FileNotFoundError(source)
    if destination.exists():
        raise FileExistsError(destination)

    data = source.read_bytes()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(data)

    if destination.read_bytes() != data:
        raise IOError("Backup verification failed")

    return {
        "backup": str(destination),
        "checksum": checksum(data),
        "verified": True,
    }

def deploy(*args, **kwargs):
    raise PermissionError("Live deployment disabled")

def activate(*args, **kwargs):
    raise PermissionError("Live activation disabled")

def rollback(*args, **kwargs):
    raise PermissionError("Live rollback disabled")
