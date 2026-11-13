# Home Intelligence Manager V1.0

Home Assistant integration for automation suggestions, validation
and administrator approval.

## Installation

1. Back up your Home Assistant configuration.
2. Copy `custom_components/ai_automation_suggester` into the
   Home Assistant `config/custom_components` directory.
3. Restart Home Assistant.
4. Configure the integration through Home Assistant.

Existing installations must be backed up before upgrading.

## Safety

Live automation deployment, activation and rollback are disabled.
Approval does not automatically deploy an automation.

## Compatibility

The internal integration domain remains `ai_automation_suggester`
to preserve compatibility with existing installations.

## Dependencies

See the integration's `manifest.json`.
Some AI providers may require separate credentials or payment.

## Verification

The staging test suite passed 12 tests.
These tests do not establish full Home Assistant runtime compatibility.
