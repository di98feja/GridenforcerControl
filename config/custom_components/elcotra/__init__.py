"""The ElCoTra integration for Home Assistant."""

from __future__ import annotations

import asyncio
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_ENERGY_SENSORS, DOMAIN
from .coordinator import ElCoTraCoordinator
from .csv_services import async_setup_services as async_setup_csv_services

PLATFORMS = ["sensor"]
_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up ElCoTra from a config entry."""
    coordinator = ElCoTraCoordinator(hass, entry)

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    # Set up platforms FIRST so sensors can restore state
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Then start coordinator AFTER sensors have had chance to restore
    await coordinator.async_start()

    # Setup CSV import service (only once for all entries)
    async_setup_csv_services(hass)

    # Trigger automatic CSV import if configured
    if entry.data.get("auto_import_on_setup", False):
        _LOGGER.info("Auto import on setup is enabled, scheduling CSV import")
        hass.async_create_task(_async_auto_import_csv(hass, entry))

    return True


async def _async_auto_import_csv(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Automatically import CSV data on setup.

    Args:
        hass: Home Assistant instance
        entry: Config entry with CSV URLs
    """
    # Wait a bit for sensors to initialize
    await asyncio.sleep(5)

    _LOGGER.info("Starting automatic CSV import")

    # Build CSV URLs and target sensors from config
    csv_urls = {}
    target_sensors = {}

    # Map CSV URLs to phases based on energy sensors
    energy_sensors = entry.data.get(CONF_ENERGY_SENSORS, [])

    if entry.data.get("csv_url_l1") and len(energy_sensors) >= 1:
        csv_urls["l1"] = entry.data["csv_url_l1"]
        target_sensors["l1"] = energy_sensors[0]

    if entry.data.get("csv_url_l2") and len(energy_sensors) >= 2:
        csv_urls["l2"] = entry.data["csv_url_l2"]
        target_sensors["l2"] = energy_sensors[1]

    if entry.data.get("csv_url_l3") and len(energy_sensors) >= 3:
        csv_urls["l3"] = entry.data["csv_url_l3"]
        target_sensors["l3"] = energy_sensors[2]

    if not csv_urls:
        _LOGGER.warning("No CSV URLs configured for auto import")
        return

    _LOGGER.info(
        "Auto importing from %d CSV URLs: %s",
        len(csv_urls),
        ", ".join(csv_urls.keys()),
    )

    # Call the CSV import service
    try:
        await hass.services.async_call(
            DOMAIN,
            "import_csv_data",
            {
                "csv_urls": csv_urls,
                "target_sensors": target_sensors,
                "options": {
                    "apply_to_cost_sensors": True,
                    "recalculate_statistics": True,
                    "backup_existing": False,
                },
            },
            blocking=True,
        )
        _LOGGER.info("Automatic CSV import completed successfully")
    except Exception as err:  # noqa: BLE001
        _LOGGER.error("Automatic CSV import failed: %s", err)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    coordinator: ElCoTraCoordinator = hass.data[DOMAIN][entry.entry_id]

    # Stoppa schemaläggning
    await coordinator.async_stop()

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
