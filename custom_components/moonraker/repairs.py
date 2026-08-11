"""Repairs support for the Moonraker integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components.repairs import RepairsFlow, RepairsFlowResult
from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntry, ConfigFlowContext
from homeassistant.core import HomeAssistant
from homeassistant.helpers.issue_registry import IssueSeverity, async_create_issue

from .const import DOMAIN

INVALID_API_KEY_ISSUE = "invalid_api_key"


async def create_invalid_api_key_issue(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Create a repair issue telling the user the API key is invalid."""
    async_create_issue(
        hass,
        DOMAIN,
        f"{INVALID_API_KEY_ISSUE}_{entry.entry_id}",
        data={"entry_id": entry.entry_id},
        is_fixable=True,
        is_persistent=False,
        severity=IssueSeverity.ERROR,
        translation_key=INVALID_API_KEY_ISSUE,
        translation_placeholders={"entry_title": entry.title},
    )


async def async_create_fix_flow(
    hass: HomeAssistant,
    issue_id: str,
    data: dict[str, str | int | float | None] | None,
) -> RepairsFlow:
    """Create a fix flow for a Moonraker repair issue."""
    return MoonrakerInvalidApiKeyRepairFlow()


class MoonrakerInvalidApiKeyRepairFlow(RepairsFlow):
    """Repair flow that guides the user to reauthenticate."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> RepairsFlowResult:
        """Show the reauthentication confirmation step."""
        return self.async_show_form(
            step_id="confirm",
            data_schema=vol.Schema(
                {
                    vol.Required("reauth"): bool,
                }
            ),
        )

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> RepairsFlowResult:
        """Start the reauthentication flow when the user confirms."""
        if user_input and user_input.get("reauth") and self.data:
            entry_id = str(self.data.get("entry_id", ""))
            if entry_id:
                context = ConfigFlowContext(source=SOURCE_REAUTH, entry_id=entry_id)
                await self.hass.config_entries.flow.async_init(DOMAIN, context=context)
        return self.async_create_entry(title="", description="", data={})
