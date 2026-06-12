"""Calculation functions for ElCoTra."""

from __future__ import annotations

from datetime import datetime, timedelta
import logging

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.history import get_significant_states
from homeassistant.components.recorder.statistics import (
    async_import_statistics,
    statistics_during_period,
)
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .const import TARIFF_TYPE_FIXED, UPDATE_INTERVAL_SECONDS

_LOGGER = logging.getLogger(__name__)


async def calculate_period_cost(
    hass: HomeAssistant,
    energy_sensors: list[str],
    tariff_type: str,
    fixed_tariff: float,
    tariff_sensor: str | None,
    start_time: datetime,
    end_time: datetime,
) -> dict:
    """Calculate the cost for a given period."""
    # Steg 1: Hämta start och slut energivärden
    energy_start = await get_energy_at_time(hass, energy_sensors, start_time)
    energy_end = await get_energy_at_time(hass, energy_sensors, end_time)
    total_energy = energy_end - energy_start

    # Om fixed tariff, enkel beräkning
    if tariff_type == TARIFF_TYPE_FIXED:
        return {
            "energy_kwh": total_energy,
            "cost": total_energy * fixed_tariff,
            "avg_tariff": fixed_tariff,
        }
    if tariff_sensor is None:
        raise ValueError("Need tariff_sensor for time based tariff")

    tariffs = await get_tariff_for_period(hass, tariff_sensor, start_time, end_time)

    accumulated_cost = 0.0
    sum_tariff = 0.0

    for i, (period_start_time, tariff_value) in enumerate(tariffs):
        # Period end
        if i + 1 < len(tariffs):
            period_end_time = tariffs[i + 1][0]
        else:
            period_end_time = end_time

        # Energi för perioden
        energy_at_start = await get_energy_at_time(
            hass, energy_sensors, period_start_time
        )
        energy_at_end = await get_energy_at_time(hass, energy_sensors, period_end_time)
        energy_used = energy_at_end - energy_at_start

        cost = energy_used * tariff_value
        accumulated_cost += cost
        print(  # noqa: T201
            f"{period_start_time} → {period_end_time}: {energy_used} kWh × {tariff_value} = {cost} kr"
        )
        sum_tariff += tariff_value

    return {
        "energy_kwh": total_energy,
        "cost": accumulated_cost,
        "avg_tariff": sum_tariff / len(tariffs) if tariffs else 0.0,
    }


async def get_energy_at_time(
    hass: HomeAssistant, energy_sensors: list[str], at: datetime
) -> float:
    """Calculate total accumulated energy up to a specific time."""
    start = at - timedelta(hours=1)
    total_energy = 0.0
    for entity_id in energy_sensors:
        states = await get_instance(hass).async_add_executor_job(
            get_significant_states,
            hass,
            start,
            at,
            [entity_id],
        )
        if not states or entity_id not in states:
            continue
        entity_states = states[entity_id]
        if not entity_states:
            continue
        last_state = entity_states[-1]
        # State may be a dict from recorder history or a State object; handle both
        if last_state is None:
            continue
        if isinstance(last_state, dict):
            state_value = last_state.get("state")
        else:
            state_value = getattr(last_state, "state", None)
        if state_value in ("unknown", "unavailable") or state_value is None:
            continue

        total_energy += float(state_value)
    return total_energy


async def get_tariff_for_period(
    hass: HomeAssistant, tariff_sensor: str, start: datetime, end: datetime
) -> list[tuple[datetime, float]]:
    """Retreive all tariff values during specific period."""
    states = await get_instance(hass).async_add_executor_job(
        get_significant_states,
        hass,
        start,
        end,
        [tariff_sensor],
    )
    if not states or tariff_sensor not in states:
        raise ValueError("No states found for tariff sensor")
    entity_states = states[tariff_sensor]
    if not entity_states:
        raise ValueError("No states found for tariff sensor")

    tariff_data = []
    for state in entity_states:
        # Hantera både State-objekt och dict
        if isinstance(state, dict):
            state_value = state.get("state")
            last_changed = state.get("last_changed")
        else:
            state_value = state.state
            last_changed = state.last_changed

        # Skippa ogiltiga states
        if state_value in ("unknown", "unavailable") or state_value is None:
            continue

        if last_changed is None:
            continue

        try:
            tariff_value = float(state_value)
            # Konvertera last_changed till datetime om det är sträng
            if isinstance(last_changed, str):
                timestamp = dt_util.parse_datetime(last_changed)
            else:
                timestamp = last_changed

            tariff_data.append((timestamp, tariff_value))
        except (ValueError, TypeError):
            continue

    if not tariff_data:
        raise ValueError(f"No valid tariff data found for {tariff_sensor}")

    return tariff_data


async def import_historical_statistics(  # noqa: C901
    hass: HomeAssistant,
    entry_id: str,
    statistic_id: str,
    unit: str,
    energy_sensors: list[str],
    tariff_type: str,
    fixed_tariff: float,
    tariff_sensor: str | None,
    start_date: datetime,
    end_date: datetime,
    fallback_tariff: float | None = None,
) -> dict:
    """Import historical cost statistics to Home Assistant recorder.

    Returns dict with:
        - entries_created: Number of statistics entries created
        - total_cost: Total accumulated cost
        - total_energy: Total energy consumed
        - errors: List of error messages (if any)
    """
    _LOGGER.info(
        "Starting historical import from %s to %s",
        start_date.isoformat(),
        end_date.isoformat(),
    )

    # Ensure start_date is at midnight
    start_date = dt_util.start_of_local_day(start_date)
    # Ensure end_date includes the full day
    if end_date.hour == 0 and end_date.minute == 0:
        end_date = end_date.replace(hour=23, minute=59, second=59)

    # Determine effective fallback tariff
    effective_fallback = (
        fallback_tariff if fallback_tariff is not None else fixed_tariff
    )

    # IMPORTANT: Get existing statistics to find baseline cost
    # We need to ADD to existing data, not replace it
    _LOGGER.info("Checking for existing statistics before import period...")
    baseline_cost = 0.0

    try:
        existing_stats = await get_instance(hass).async_add_executor_job(
            statistics_during_period,
            hass,
            start_date - timedelta(days=1),  # Look back 1 day
            start_date,
            {statistic_id},
            "hour",
            None,
            {"sum"},
        )

        if existing_stats and statistic_id in existing_stats:
            # Get the last value before our import period
            stats_list = existing_stats[statistic_id]
            if stats_list:
                last_stat = stats_list[-1]
                if last_stat and "sum" in last_stat:
                    baseline_cost = last_stat["sum"]
                    _LOGGER.info(
                        "Found existing statistics baseline: %.2f %s at %s",
                        baseline_cost,
                        unit,
                        last_stat.get("start"),
                    )
    except (ValueError, TypeError, KeyError) as err:
        _LOGGER.warning("Could not fetch existing statistics: %s. Starting from 0.", err)

    statistics = []
    accumulated_cost = baseline_cost  # Start from existing baseline!
    total_energy_consumed = 0.0
    errors = []
    entries_created = 0

    # Calculate 15-minute intervals
    interval = timedelta(seconds=UPDATE_INTERVAL_SECONDS)

    # OPTIMIZATION: Fetch ALL historical data in bulk (one DB call per sensor)
    _LOGGER.info("Fetching historical energy data in bulk...")
    energy_history = {}
    for entity_id in energy_sensors:
        try:
            states = await get_instance(hass).async_add_executor_job(
                get_significant_states,
                hass,
                start_date - timedelta(hours=1),  # Buffer for first reading
                end_date + timedelta(hours=1),  # Buffer for last reading
                [entity_id],
            )
            if states and entity_id in states:
                energy_history[entity_id] = states[entity_id]
                _LOGGER.info(
                    "Loaded %d history records for %s",
                    len(states[entity_id]),
                    entity_id,
                )
            else:
                energy_history[entity_id] = []
                _LOGGER.warning("No history data found for %s", entity_id)
        except (ValueError, TypeError, KeyError) as err:
            _LOGGER.warning("Failed to load history for %s: %s", entity_id, err)
            energy_history[entity_id] = []

    # Check if we have any data at all
    total_records = sum(len(states) for states in energy_history.values())
    if total_records == 0:
        error_msg = "No energy history data found for the specified period"
        _LOGGER.error(error_msg)
        errors.append(error_msg)
        return {
            "entries_created": 0,
            "total_cost": 0.0,
            "total_energy": 0.0,
            "errors": errors,
        }

    # OPTIMIZATION: Fetch tariff history in bulk if using sensor
    tariff_history = []
    if tariff_type != TARIFF_TYPE_FIXED and tariff_sensor:
        _LOGGER.info("Fetching tariff history in bulk...")
        try:
            states = await get_instance(hass).async_add_executor_job(
                get_significant_states,
                hass,
                start_date,
                end_date,
                [tariff_sensor],
            )
            if states and tariff_sensor in states:
                # Parse tariff data
                for state in states[tariff_sensor]:
                    if isinstance(state, dict):
                        state_value = state.get("state")
                        last_changed = state.get("last_changed")
                    else:
                        state_value = state.state
                        last_changed = state.last_changed

                    if state_value in ("unknown", "unavailable") or state_value is None:
                        continue

                    try:
                        tariff_value = float(state_value)
                        if isinstance(last_changed, str):
                            timestamp = dt_util.parse_datetime(last_changed)
                        else:
                            timestamp = last_changed
                        tariff_history.append((timestamp, tariff_value))
                    except (ValueError, TypeError):
                        continue

                _LOGGER.info("Loaded %d tariff history records", len(tariff_history))
        except (ValueError, TypeError, KeyError) as err:
            _LOGGER.warning("Failed to load tariff history: %s", err)

    # Build indexed lookup for faster access
    _LOGGER.info("Building energy lookup index...")
    energy_index = {}
    for entity_id, states in energy_history.items():
        sorted_states = []
        for state in states:
            if isinstance(state, dict):
                state_time = state.get("last_changed")
                state_value = state.get("state")
                if isinstance(state_time, str):
                    state_time = dt_util.parse_datetime(state_time)
            else:
                state_time = state.last_changed
                state_value = state.state

            if state_time and state_value not in ("unknown", "unavailable"):
                try:
                    value = float(state_value)
                    sorted_states.append((state_time, value))
                except (ValueError, TypeError):
                    continue

        # Sort by timestamp for binary search
        sorted_states.sort(key=lambda x: x[0])
        energy_index[entity_id] = sorted_states
        _LOGGER.debug("Indexed %d valid states for %s", len(sorted_states), entity_id)

    def _get_energy_from_cache(target_time: datetime) -> float:
        """Get energy at specific time from cached history using binary search."""
        total = 0.0
        for sorted_states in energy_index.values():
            if not sorted_states:
                continue

            # Binary search for the last state before or at target_time
            left, right = 0, len(sorted_states) - 1
            result_idx = -1

            while left <= right:
                mid = (left + right) // 2
                if sorted_states[mid][0] <= target_time:
                    result_idx = mid
                    left = mid + 1
                else:
                    right = mid - 1

            if result_idx >= 0:
                total += sorted_states[result_idx][1]

        return total

    def _get_tariff_for_time(target_time: datetime) -> float:
        """Get tariff at specific time from cached history."""
        if tariff_type == TARIFF_TYPE_FIXED:
            return fixed_tariff

        if not tariff_history:
            return effective_fallback

        # Find last tariff change before target_time
        current_tariff = effective_fallback
        for timestamp, tariff_value in tariff_history:
            if timestamp <= target_time:
                current_tariff = tariff_value
            else:
                break  # Tariff history is chronological

        return current_tariff

    # Process intervals using cached data
    _LOGGER.info("Processing intervals...")
    current_time = start_date
    iterations = 0
    max_iterations = 100000  # Safety limit (about 7 years of 15-min intervals)

    while current_time < end_date and iterations < max_iterations:
        next_time = min(current_time + interval, end_date)
        iterations += 1

        # Progress logging every 1000 iterations (even if no data)
        if iterations % 1000 == 0:
            _LOGGER.info(
                "Processing iteration %d at %s (created %d entries so far)",
                iterations,
                current_time.isoformat(),
                entries_created,
            )

        try:
            # Get energy from cache
            energy_start = _get_energy_from_cache(current_time)
            energy_end = _get_energy_from_cache(next_time)

            # Skip if we don't have data
            if energy_start == 0.0 and energy_end == 0.0:
                current_time = next_time
                continue

            period_energy = energy_end - energy_start

            # Skip negative periods (can happen with resets)
            if period_energy < 0:
                _LOGGER.debug(
                    "Skipping negative energy period at %s", current_time.isoformat()
                )
                current_time = next_time
                continue

            # Get tariff from cache
            period_tariff = _get_tariff_for_time(current_time)

            # Calculate cost
            period_cost = period_energy * period_tariff
            accumulated_cost += period_cost
            total_energy_consumed += period_energy

            # Create statistics entry ONLY at the top of the hour
            # Statistics API requires timestamps at hour boundaries
            hour_start = current_time.replace(minute=0, second=0, microsecond=0)

            # Only add statistics entry if we're at the start of an hour
            # OR if this is the last interval (to capture partial hours)
            if current_time.minute == 0 or next_time == end_date:
                statistics.append(
                    {
                        "start": hour_start,
                        "state": accumulated_cost,
                        "sum": accumulated_cost,
                    }
                )
                entries_created += 1

                if entries_created % 25 == 0:  # Log every 25 hours instead of 100
                    _LOGGER.info(
                        "Processed %d hourly entries, accumulated cost: %.2f %s",
                        entries_created,
                        accumulated_cost,
                        unit,
                    )

        except (ValueError, TypeError, KeyError) as err:
            error_msg = f"Error processing period {current_time.isoformat()}: {err}"
            _LOGGER.warning(error_msg)
            errors.append(error_msg)

        current_time = next_time

    if iterations >= max_iterations:
        error_msg = f"Reached maximum iterations ({max_iterations}), stopping import"
        _LOGGER.error(error_msg)
        errors.append(error_msg)

    # Import statistics to recorder
    if statistics:
        _LOGGER.info("Importing %d statistics entries to database...", entries_created)
        metadata = {
            "source": "recorder",
            "statistic_id": statistic_id,
            "name": None,  # Will use entity's name
            "unit_of_measurement": unit,
            "has_mean": False,
            "has_sum": True,
        }

        try:
            async_import_statistics(hass, metadata, statistics)
            _LOGGER.info(
                "Successfully imported %d statistics entries. Total cost: %.2f %s, Total energy: %.2f kWh",
                entries_created,
                accumulated_cost,
                unit,
                total_energy_consumed,
            )
        except (ValueError, TypeError, KeyError) as err:
            error_msg = f"Failed to import statistics: {err}"
            _LOGGER.error(error_msg)
            errors.append(error_msg)
    else:
        _LOGGER.warning("No statistics to import - check if energy sensors have data")

    return {
        "entries_created": entries_created,
        "total_cost": accumulated_cost,
        "total_energy": total_energy_consumed,
        "errors": errors,
    }
