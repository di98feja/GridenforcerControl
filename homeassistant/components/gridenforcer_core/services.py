"""Service handlers for Gridenforcer Core integration."""

from __future__ import annotations

import logging

from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


def async_setup_services(hass: HomeAssistant) -> None:
    """Set up services for Gridenforcer Core integration."""
    # Services will be added here as needed for gridenforcer_core functionality
    _LOGGER.info("Gridenforcer Core services initialized")
