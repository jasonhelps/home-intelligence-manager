
import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INTEGRATION = ROOT / "integration" / "ai_automation_suggester"

class TestIntegration(unittest.TestCase):
    def test_required_modules(self):
        for name in (
            "__init__.py",
            "api.py",
            "approval_api.py",
            "manager/controller.py",
            "manager/validator.py",
            "manager/deployment_engine.py",
        ):
            with self.subTest(module=name):
                ast.parse((INTEGRATION / name).read_text())

    def test_api_registration(self):
        source = (INTEGRATION / "api.py").read_text()
        self.assertIn("register_view", source)

    def test_deployment_safety(self):
        source = (INTEGRATION / "manager/deployment_engine.py").read_text()
        self.assertIn('"deployment_enabled": False', source)
        self.assertIn('"approval_required": True', source)
        self.assertIn('"ready_to_apply": False', source)

if __name__ == "__main__":
    unittest.main()
