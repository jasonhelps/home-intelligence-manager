
import sys
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
import types

integration = ROOT / "integration" / "ai_automation_suggester"
package = types.ModuleType("ai_automation_suggester")
package.__path__ = [str(integration)]
sys.modules["ai_automation_suggester"] = package

manager = types.ModuleType("ai_automation_suggester.manager")
manager.__path__ = [str(integration / "manager")]
sys.modules["ai_automation_suggester.manager"] = manager

from ai_automation_suggester.manager import (
    approval, approval_store, controller, validator, deployment_engine
)

AUTOMATION = {
    "alias": "Test automation",
    "triggers": [{"trigger": "state", "entity_id": "binary_sensor.test"}],
    "actions": [{"action": "light.turn_on",
                 "target": {"entity_id": "light.test"}}],
}
SERVICES = {"light.turn_on"}
ENTITIES = {"binary_sensor.test", "light.test"}


class TestManagerWorkflow(unittest.TestCase):
    def test_valid_proposal(self):
        result = controller.validate_proposal(AUTOMATION, SERVICES, ENTITIES)
        self.assertTrue(result["valid"])

    def test_invalid_service(self):
        result = controller.validate_proposal(AUTOMATION, set(), ENTITIES)
        self.assertFalse(result["valid"])

    def test_invalid_entity(self):
        result = controller.validate_proposal(AUTOMATION, SERVICES, set())
        self.assertFalse(result["valid"])

    def test_approval_integrity(self):
        proposal = approval.prepare(AUTOMATION.copy())
        with self.assertRaises(PermissionError):
            approval.approve(proposal, "invalid")
        approval.approve(proposal, proposal["fingerprint"])
        self.assertTrue(approval.verify(proposal))

    def test_expired_approval(self):
        proposal = approval.prepare(AUTOMATION.copy())
        proposal["created_at"] -= approval.APPROVAL_LIFETIME + 1
        with self.assertRaises(PermissionError):
            approval.approve(proposal, proposal["fingerprint"])

    def test_approval_store_lifecycle(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            with patch.object(approval_store, "STORE", base / "approvals.json"):
                record = approval_store.register(
                    AUTOMATION, SERVICES, ENTITIES, "test-suggestion"
                )
                approval_id = record["approval_id"]
                self.assertEqual(record["status"], "pending")

                with self.assertRaises(PermissionError):
                    approval_store.transition(
                        approval_id, "approve", {"alias": "Changed"}
                    )

                approved = approval_store.transition(
                    approval_id, "approve", AUTOMATION
                )
                self.assertEqual(approved["status"], "approved")

                with self.assertRaises(PermissionError):
                    approval_store.transition(approval_id, "reject")

    def test_rejection(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(
                approval_store, "STORE", Path(directory) / "approvals.json"
            ):
                record = approval_store.register(
                    AUTOMATION, SERVICES, ENTITIES
                )
                rejected = approval_store.transition(
                    record["approval_id"], "reject"
                )
                self.assertEqual(rejected["status"], "rejected")

    def test_deployment_blocked(self):
        for function in (
            deployment_engine.deploy,
            deployment_engine.activate,
            deployment_engine.rollback,
            approval.deploy,
            approval.activate,
        ):
            with self.subTest(function=function.__name__):
                with self.assertRaises(PermissionError):
                    function(None)

        with self.assertRaises(PermissionError):
            controller.create_disabled(None, None, None, None)

    def test_backup_integrity(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "original"
            backup = Path(directory) / "backup"
            source.write_bytes(b"test automation")
            result = deployment_engine.prepare_backup(source, backup)
            self.assertTrue(result["verified"])
            self.assertEqual(source.read_bytes(), backup.read_bytes())


if __name__ == "__main__":
    unittest.main()
