"""AI Automation Manager approval and deployment controller."""

import hashlib
import json

from .approval import fingerprint
from .validator import validate_complete

DEPLOYMENT_ENABLED = False
ACTIVATION_ENABLED = False


def validate_proposal(automation, services, entities):
    """Independently validate the proposed automation."""
    import yaml

    if not isinstance(automation, dict):
        raise ValueError("Automation must be a dictionary")

    result = validate_complete(
        yaml.safe_dump(automation, sort_keys=False),
        services,
        entities
    )

    return {
        "valid": bool(result.get("valid"))
                 and not result.get("errors")
                 and not result.get("warnings"),
        "errors": result.get("errors", []),
        "warnings": result.get("warnings", []),
        "fingerprint": fingerprint(automation)
    }


def prepare_proposal(automation, services, entities, suggestion_id=None):
    """Validate before registering a proposal."""
    result = validate_proposal(automation, services, entities)

    if not result["valid"]:
        raise PermissionError("Proposal failed validation")

    from .approval_store import register

    record = register(automation, services, entities, suggestion_id)

    return {
        "approval_id": record["approval_id"],
        "status": record["status"],
        "fingerprint": record["fingerprint"],
        "validation": result,
        "deployment_enabled": False
    }


def approve_proposal(approval_id, automation):
    """Record approval without deploying anything."""
    from .approval_store import transition

    return transition(approval_id, "approve", automation)


def reject_proposal(approval_id):
    """Reject a pending proposal."""
    from .approval_store import transition

    return transition(approval_id, "reject")


def create_disabled(approval_id, automation, services, entities):
    """Fail closed until live deployment is separately authorised."""
    if not DEPLOYMENT_ENABLED:
        raise PermissionError(
            "Live deployment remains locked"
        )

    raise PermissionError(
        "Deployment integration not yet authorised"
    )


def activate_automation(automation_id):
    raise PermissionError("Live activation remains locked")


def rollback_automation(automation_id):
    raise PermissionError("Live rollback remains locked")
