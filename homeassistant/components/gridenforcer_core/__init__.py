"""The Gridenforcer Core integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN
from .services import async_setup_services

# Supported platforms
_PLATFORMS: list[Platform] = [Platform.SENSOR]

# ConfigEntry type alias
type GridenforcerConfigEntry = ConfigEntry[None]

# Config schema - this integration is config entry only
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Gridenforcer Core integration.

    This is called when the integration is loaded.
    Services are registered here (not in async_setup_entry).
    """
    # Register services
    async_setup_services(hass)

    return True


async def async_setup_entry(
    hass: HomeAssistant, entry: GridenforcerConfigEntry
) -> bool:
    """Set up Gridenforcer Core from a config entry."""
    # Set runtime data (currently None, will be used for API client in future)
    entry.runtime_data = None

    # Forward setup to platforms
    await hass.config_entries.async_forward_entry_setups(entry, _PLATFORMS)

    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: GridenforcerConfigEntry
) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, _PLATFORMS)
