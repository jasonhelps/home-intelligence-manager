"""Authenticated approval API for AI Automation Manager."""

from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.components.http.const import KEY_HASS_USER
from homeassistant.core import HomeAssistant


class AIApprovalView(HomeAssistantView):
    """Administrator-only approval endpoint."""

    url = "/api/ai_automation_suggester/approval"
    name = "api:ai_automation_suggester:approval"
    requires_auth = True

    async def post(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]

        user = request.get(KEY_HASS_USER)

        if user is None:
            return self.json(
                {"success": False, "error": "Authentication required"},
                status_code=401,
            )

        if not user.is_admin:
            return self.json(
                {"success": False, "error": "Administrator required"},
                status_code=403,
            )

        try:
            payload = await request.json()
        except (ValueError, web.HTTPException):
            return self.json(
                {"success": False, "error": "Invalid JSON"},
                status_code=400,
            )

        if not isinstance(payload, dict):
            return self.json(
                {"success": False, "error": "Expected JSON object"},
                status_code=400,
            )


        if payload.get("action") in ("approval_status", "reject_approval"):
            from .manager.approval_store import load, locked_store
            from .manager.controller import reject_proposal

            approval_id = payload.get("approval_id")
            if not isinstance(approval_id, str) or not approval_id.strip():
                return self.json(
                    {"success": False, "error": "Approval ID required"},
                    status_code=400,
                )

            def read_record():
                with locked_store():
                    return load().get(approval_id)

            record = await hass.async_add_executor_job(read_record)
            if record is None:
                return self.json(
                    {"success": False, "error": "Approval not found"},
                    status_code=404,
                )

            if payload["action"] == "approval_status":
                return self.json({
                    "success": True,
                    "approval_id": approval_id,
                    "status": record["status"],
                    "expires_at": record.get("expires_at"),
                    "deployment_enabled": False,
                })

            try:
                record = await hass.async_add_executor_job(
                    reject_proposal, approval_id
                )
            except (PermissionError, KeyError, ValueError) as error:
                return self.json(
                    {"success": False, "error": str(error)},
                    status_code=422,
                )

            return self.json({
                "success": True,
                "approval_id": approval_id,
                "status": record["status"],
                "deployment_enabled": False,
            })


        if payload.get("action") == "approve_suggestion":
            import yaml
            from .store import async_get_suggestion_store
            from .manager.approval_store import load, locked_store
            from .manager.controller import approve_proposal
            from .manager.approval import fingerprint

            approval_id = payload.get("approval_id")
            suggestion_id = payload.get("suggestion_id")

            if not isinstance(approval_id, str) or not approval_id.strip():
                return self.json(
                    {"success": False, "error": "Approval ID required"},
                    status_code=400,
                )
            if not isinstance(suggestion_id, str) or not suggestion_id.strip():
                return self.json(
                    {"success": False, "error": "Suggestion ID required"},
                    status_code=400,
                )

            def read_record():
                with locked_store():
                    return load().get(approval_id)

            record = await hass.async_add_executor_job(read_record)
            if record is None:
                return self.json(
                    {"success": False, "error": "Approval not found"},
                    status_code=404,
                )

            store = async_get_suggestion_store(hass)
            suggestions = await store.async_list()
            suggestion = next(
                (item for item in suggestions if item.get("id") == suggestion_id),
                None,
            )
            if suggestion is None:
                return self.json(
                    {"success": False, "error": "Suggestion not found"},
                    status_code=404,
                )

            try:
                automation = yaml.safe_load(suggestion.get("yamlCode", ""))
            except (yaml.YAMLError, TypeError, ValueError):
                return self.json(
                    {"success": False, "error": "Invalid suggestion YAML"},
                    status_code=400,
                )

            if not isinstance(automation, dict):
                return self.json(
                    {"success": False, "error": "Invalid automation"},
                    status_code=400,
                )

            if record.get("suggestion_id") != suggestion_id:
                return self.json(
                    {"success": False, "error": "Approval belongs to another suggestion"},
                    status_code=409,
                )

            if fingerprint(automation) != record["fingerprint"]:
                return self.json(
                    {"success": False, "error": "Proposal changed"},
                    status_code=409,
                )

            try:
                result = await hass.async_add_executor_job(
                    approve_proposal, approval_id, automation
                )
            except (PermissionError, KeyError, ValueError) as error:
                return self.json(
                    {"success": False, "error": str(error)},
                    status_code=422,
                )

            return self.json({
                "success": True,
                "approval_id": approval_id,
                "status": result["status"],
                "deployment_enabled": False,
            })

        if payload.get("action") == "prepare_suggestion":
            suggestion_id = payload.get("suggestion_id")
            if not isinstance(suggestion_id, str) or not suggestion_id.strip():
                return self.json(
                    {"success": False, "error": "Valid suggestion ID required"},
                    status_code=400,
                )

            from .store import async_get_suggestion_store
            from .manager.controller import prepare_proposal
            import yaml

            store = async_get_suggestion_store(hass)
            suggestions = await store.async_list()
            suggestion = next(
                (item for item in suggestions
                 if item.get("id") == suggestion_id),
                None,
            )

            if suggestion is None:
                return self.json(
                    {"success": False, "error": "Suggestion not found"},
                    status_code=404,
                )

            yaml_code = suggestion.get("yamlCode")
            if not isinstance(yaml_code, str) or not yaml_code.strip():
                return self.json(
                    {"success": False, "error": "Suggestion has no YAML"},
                    status_code=400,
                )

            try:
                automation = yaml.safe_load(yaml_code)
            except yaml.YAMLError:
                return self.json(
                    {"success": False, "error": "Invalid suggestion YAML"},
                    status_code=400,
                )

            if not isinstance(automation, dict):
                return self.json(
                    {"success": False, "error": "Expected automation mapping"},
                    status_code=400,
                )

            services = {
                domain + "." + service
                for domain, available in hass.services.async_services().items()
                for service in available
            }
            entities = set(hass.states.async_entity_ids())

            try:
                result = await hass.async_add_executor_job(
                    prepare_proposal, automation, services, entities, suggestion_id
                )
            except (PermissionError, ValueError, TypeError) as error:
                return self.json(
                    {
                        "success": False,
                        "error": str(error),
                        "deployment_enabled": False,
                    },
                    status_code=422,
                )

            return self.json({
                "success": True,
                "suggestion_id": suggestion_id,
                "approval": result,
                "deployment_enabled": False,
            })

        if payload.get("action") == "validate_suggestion":
            suggestion_id = payload.get("suggestion_id")
            if not isinstance(suggestion_id, str) or not suggestion_id.strip():
                return self.json(
                    {"success": False, "error": "Valid suggestion ID required"},
                    status_code=400,
                )

            from .store import async_get_suggestion_store
            from .manager.controller import validate_proposal
            import yaml

            store = async_get_suggestion_store(hass)
            suggestions = await store.async_list()

            suggestion = next(
                (
                    item for item in suggestions
                    if item.get("id") == suggestion_id
                ),
                None,
            )

            if suggestion is None:
                return self.json(
                    {"success": False, "error": "Suggestion not found"},
                    status_code=404,
                )

            yaml_code = suggestion.get("yamlCode")

            if not isinstance(yaml_code, str) or not yaml_code.strip():
                return self.json(
                    {"success": False, "error": "Suggestion has no YAML"},
                    status_code=400,
                )

            try:
                automation = yaml.safe_load(yaml_code)
            except yaml.YAMLError:
                return self.json(
                    {"success": False, "error": "Invalid suggestion YAML"},
                    status_code=400,
                )

            if not isinstance(automation, dict):
                return self.json(
                    {"success": False, "error": "Expected automation mapping"},
                    status_code=400,
                )

            services = {
                domain + "." + service
                for domain, available in hass.services.async_services().items()
                for service in available
            }

            entities = set(hass.states.async_entity_ids())

            try:
                result = validate_proposal(
                    automation, services, entities
                )
            except (ValueError, TypeError):
                return self.json(
                    {"success": False, "error": "Validation failed"},
                    status_code=400,
                )

            return self.json({
                "success": True,
                "suggestion_id": suggestion_id,
                "validation": result,
                "approval_required": True,
                "deployment_enabled": False,
            })

        if payload.get("action") == "validate":
            automation = payload.get("automation")
            if not isinstance(automation, dict):
                return self.json(
                    {"success": False, "error": "Invalid automation"},
                    status_code=400,
                )

            from .manager.controller import validate_proposal

            services = set()
            for domain, domain_services in hass.services.async_services().items():
                for service in domain_services:
                    services.add(domain + "." + service)

            entities = set(hass.states.async_entity_ids())

            try:
                result = validate_proposal(automation, services, entities)
            except (ValueError, TypeError) as error:
                return self.json(
                    {"success": False, "error": str(error)},
                    status_code=400,
                )

            return self.json({
                "success": True,
                "validation": result,
                "deployment_enabled": False,
            })

        return self.json(
            {
                "success": False,
                "status": "not_enabled",
                "message": "Approval execution is not yet enabled",
                "deployment_enabled": False,
            },
            status_code=503,
        )
