"""Read-only structural validation of proposed HA automations."""

import yaml


def validate_automation(yaml_text):
    try:
        automation = yaml.safe_load(yaml_text)
    except yaml.YAMLError as error:
        return False, "Invalid YAML: {}".format(error)

    if not isinstance(automation, dict):
        return False, "Automation must be a YAML mapping"

    if not isinstance(automation.get("alias"), str) or not automation["alias"].strip():
        return False, "Missing automation name"

    triggers = automation.get("triggers", automation.get("trigger"))
    actions = automation.get("actions", automation.get("action"))

    if not isinstance(triggers, list) or not triggers:
        return False, "Missing or invalid triggers"

    if not isinstance(actions, list) or not actions:
        return False, "Missing or invalid actions"

    return True, "Basic structure passed; deployment not authorised"


if __name__ == "__main__":
    sample = """
alias: Test Automation
triggers:
  - trigger: state
    entity_id: binary_sensor.example
    to: "on"
actions:
  - action: light.turn_on
    target:
      entity_id: light.example
"""
    valid, message = validate_automation(sample)
    print(("PASS" if valid else "FAIL") + " - " + message)


def check_services(automation, available_services):
    """Check action services, including nested action sequences."""
    missing = set()

    def inspect_actions(actions):
        for action in actions:
            if not isinstance(action, dict):
                continue

            service = action.get("action", action.get("service"))
            if isinstance(service, str) and "." in service:
                if "{{" in service or "{%" in service:
                    missing.add("Dynamic service requires manual review")
                elif service not in available_services:
                    missing.add(service)

            for key in ("sequence", "default", "then", "else"):
                nested = action.get(key)
                if isinstance(nested, list):
                    inspect_actions(nested)

            for choice in action.get("choose", []):
                if isinstance(choice, dict):
                    inspect_actions(choice.get("sequence", []))

            repeat = action.get("repeat")
            if isinstance(repeat, dict):
                inspect_actions(repeat.get("sequence", []))

    inspect_actions(automation.get("actions", automation.get("action", [])))
    return sorted(missing)


def check_entities(automation, available_entities):
    """Find missing entity references throughout an automation."""
    missing = set()
    manual_review = set()

    def inspect(value, key=None):
        if isinstance(value, dict):
            for child_key, child_value in value.items():
                inspect(child_value, child_key)

        elif isinstance(value, list):
            for item in value:
                inspect(item, key)

        elif isinstance(value, str):
            if "{{" in value or "{%" in value:
                manual_review.add("Dynamic template requires manual review")
                return

            if key == "entity_id":
                for entity_id in value.split(","):
                    entity_id = entity_id.strip()
                    if entity_id and entity_id not in available_entities:
                        missing.add(entity_id)

    inspect(automation)

    return {
        "missing": sorted(missing),
        "manual_review": sorted(manual_review)
    }


def validate_complete(yaml_text, available_services, available_entities):
    """Validate a proposed automation without deploying it."""
    valid, message = validate_automation(yaml_text)

    result = {
        "valid": False,
        "errors": [],
        "warnings": [],
        "ready_to_deploy": False
    }

    if not valid:
        result["errors"].append(message)
        return result

    automation = yaml.safe_load(yaml_text)

    missing_services = check_services(automation, available_services)
    entity_result = check_entities(automation, available_entities)

    if missing_services:
        result["errors"].extend(
            "Unknown service: " + service
            for service in missing_services
        )

    if entity_result["missing"]:
        result["errors"].extend(
            "Unknown entity: " + entity
            for entity in entity_result["missing"]
        )

    result["warnings"].extend(entity_result["manual_review"])

    result["valid"] = not result["errors"] and not result["warnings"]

    return result
