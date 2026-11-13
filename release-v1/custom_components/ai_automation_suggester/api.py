"""HTTP API endpoints for stored automation suggestions."""

from __future__ import annotations

from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant

from .store import async_get_suggestion_store


class AISuggestionsView(HomeAssistantView):
    """Return stored suggestions for Lovelace cards and dashboards."""

    url = "/api/ai_automation_suggester/suggestions"
    name = "api:ai_automation_suggester:suggestions"
    requires_auth = True

    async def get(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        store = async_get_suggestion_store(hass)
        return self.json(await store.async_list())


class AISuggestionActionView(HomeAssistantView):
    """Update a suggestion action from the existing custom card."""

    url = "/api/ai_automation_suggester/{action}/{suggestion_id}"
    name = "api:ai_automation_suggester:suggestion_action"
    requires_auth = True

    async def post(self, request: web.Request, action: str, suggestion_id: str) -> web.Response:
        status_map = {
            "accept": "accepted",
            "decline": "declined",
            "dismiss": "dismissed",
        }
        if action not in status_map:
            return self.json({"success": False, "error": "Unsupported action"}, status_code=400)

        hass: HomeAssistant = request.app["hass"]
        store = async_get_suggestion_store(hass)
        suggestion = await store.async_update_status(suggestion_id, status_map[action])
        if suggestion is None:
            return self.json({"success": False, "error": "Suggestion not found"}, status_code=404)
        return self.json({"success": True, "suggestion": suggestion})



class AIApprovalListView(HomeAssistantView):
    """List existing approvals for administrators."""

    url = "/api/ai_automation_suggester/approvals"
    name = "api:ai_automation_suggester:approvals"
    requires_auth = True

    async def get(self, request: web.Request) -> web.Response:
        from homeassistant.components.http.const import KEY_HASS_USER
        from .manager.approval_store import load, locked_store, now

        user = request.get(KEY_HASS_USER)
        if user is None or not user.is_admin:
            return self.json(
                {"success": False, "error": "Administrator required"},
                status_code=403
            )

        hass = request.app["hass"]

        def read_approvals():
            from datetime import datetime
            with locked_store():
                records = list(load().values())

            result = []
            for record in records:
                item = dict(record)
                if item.get("status") == "pending":
                    expiry = item.get("expires_at")
                    try:
                        if expiry and now() >= datetime.fromisoformat(expiry):
                            item["status"] = "expired"
                    except (ValueError, TypeError):
                        item["status"] = "expired"
                result.append(item)
            return result

        records = await hass.async_add_executor_job(read_approvals)
        return self.json({
            "success": True,
            "approvals": records,
            "deployment_enabled": False
        })


def async_register_http_views(hass: HomeAssistant) -> None:
    """Register HTTP API views."""

    hass.http.register_view(AISuggestionsView())
    hass.http.register_view(AISuggestionActionView())

    from .approval_api import AIApprovalView
    hass.http.register_view(AIApprovalView())
    hass.http.register_view(AIApprovalListView())