import hashlib
import json
import time
import uuid


APPROVAL_LIFETIME = 900


def fingerprint(automation):
    canonical = json.dumps(
        automation,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def prepare(automation):
    if not isinstance(automation, dict):
        raise ValueError("Invalid automation")

    if not automation.get("alias"):
        raise ValueError("Missing automation name")

    return {
        "proposal_id": str(uuid.uuid4()),
        "automation": automation,
        "fingerprint": fingerprint(automation),
        "created_at": time.time(),
        "approved": False
    }


def approve(proposal, expected_fingerprint):
    if proposal["fingerprint"] != expected_fingerprint:
        raise PermissionError("Proposal fingerprint mismatch")

    if fingerprint(proposal["automation"]) != expected_fingerprint:
        raise PermissionError("Automation changed after preparation")

    if time.time() - proposal["created_at"] > APPROVAL_LIFETIME:
        raise PermissionError("Approval window expired")

    proposal["approved"] = True
    proposal["approved_at"] = time.time()

    return proposal


def verify(proposal):
    if not proposal.get("approved"):
        raise PermissionError("Explicit approval required")

    if fingerprint(proposal["automation"]) != proposal["fingerprint"]:
        raise PermissionError("Approved automation modified")

    if time.time() - proposal["approved_at"] > APPROVAL_LIFETIME:
        raise PermissionError("Approval expired")

    return True


def deploy(proposal):
    raise PermissionError("Deployment remains locked")


def activate(proposal):
    raise PermissionError("Activation remains locked")
