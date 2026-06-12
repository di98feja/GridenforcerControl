"""Test calculations for ElCoTra."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.elcotra.const import TARIFF_TYPE_FIXED
from custom_components.elcotra.price_calculations import (
    calculate_period_cost,
    get_energy_at_time,
    get_tariff_for_period,
)
import pytest

from homeassistant.core import HomeAssistant


@pytest.fixture
def mock_hass():
    """Create a mock HomeAssistant instance."""
    return MagicMock(spec=HomeAssistant)


async def test_get_energy_at_time_single_sensor(mock_hass):
    """Test getting energy at specific time for single sensor."""
    # Arrange
    entity_id = "sensor.test_energy"
    target_time = datetime(2024, 10, 8, 12, 0)

    # Mock get_significant_states to return test data
    mock_state = MagicMock()
    mock_state.state = "123.5"

    with patch(
        "custom_components.elcotra.price_calculations.get_instance"
    ) as mock_get_instance:
        mock_instance = MagicMock()
        mock_instance.async_add_executor_job = AsyncMock(
            return_value={entity_id: [mock_state]}
        )
        mock_get_instance.return_value = mock_instance

        # Act
        result = await get_energy_at_time(mock_hass, [entity_id], target_time)

        # Assert
        assert result == 123.5


async def test_get_energy_at_time_multiple_sensors(mock_hass):
    """Test summing energy from multiple sensors."""
    # Arrange
    entity_ids = ["sensor.energy1", "sensor.energy2"]
    target_time = datetime(2024, 10, 8, 12, 0)

    mock_state1 = MagicMock()
    mock_state1.state = "100.0"
    mock_state2 = MagicMock()
    mock_state2.state = "50.5"

    with patch(
        "custom_components.elcotra.price_calculations.get_instance"
    ) as mock_get_instance:
        mock_instance = MagicMock()
        mock_instance.async_add_executor_job = AsyncMock(
            return_value={
                entity_ids[0]: [mock_state1],
                entity_ids[1]: [mock_state2],
            }
        )
        mock_get_instance.return_value = mock_instance

        # Act
        result = await get_energy_at_time(mock_hass, entity_ids, target_time)

        # Assert
        assert result == 150.5


async def test_calculate_period_cost_fixed_tariff():
    """Test cost calculation with fixed tariff."""
    # Arrange
    mock_hass = MagicMock(spec=HomeAssistant)
    energy_sensors = ["sensor.energy"]
    tariff_sensor = "sensor.tariff"  # Not used in fixed tariff
    start_time = datetime(2024, 10, 8, 10, 0)
    end_time = datetime(2024, 10, 8, 12, 0)
    fixed_tariff = 0.20  # 0.20 currency units per kWh
    tariff_type = TARIFF_TYPE_FIXED

    with patch(
        "custom_components.elcotra.price_calculations.get_energy_at_time",
        new_callable=AsyncMock,
    ) as mock_get_energy:
        # Mock energy readings at start and end
        mock_get_energy.side_effect = [100.0, 140.0]  # 40 kWh used

        # Act
        result = await calculate_period_cost(
            mock_hass,
            energy_sensors,
            tariff_type,
            fixed_tariff,
            tariff_sensor,
            start_time,
            end_time,
        )

        # Assert
        assert result["energy_kwh"] == 40.0
        assert result["cost"] == 8.0  # 40 kWh * 0.20
        assert result["avg_tariff"] == fixed_tariff


async def test_calculate_period_cost_time_based_tariff():
    """Test cost calculation with time-based tariff."""
    # Arrange
    mock_hass = MagicMock(spec=HomeAssistant)
    energy_sensors = ["sensor.energy"]
    tariff_sensor = "sensor.tariff"
    start_time = datetime(2024, 10, 8, 10, 0)
    end_time = datetime(2024, 10, 8, 12, 0)
    fixed_tariff = 0.0
    tariff_type = "sensor"

    # Mock function that returns energy based on time
    async def mock_energy_by_time(hass, sensors, time):
        if time <= datetime(2024, 10, 8, 10, 0):
            return 100.0
        if time <= datetime(2024, 10, 8, 11, 0):
            return 120.0
        return 140.0

    with (
        patch(
            "custom_components.elcotra.price_calculations.get_energy_at_time",
            new_callable=AsyncMock,
        ) as mock_get_energy,
        patch(
            "custom_components.elcotra.price_calculations.get_tariff_for_period",
            new_callable=AsyncMock,
        ) as mock_get_tariff,
    ):
        mock_get_energy.side_effect = mock_energy_by_time

        mock_get_tariff.return_value = [
            (datetime(2024, 10, 8, 10, 0), 0.15),
            (datetime(2024, 10, 8, 11, 0), 0.25),
        ]

        # Act
        result = await calculate_period_cost(
            mock_hass,
            energy_sensors,
            tariff_type,
            fixed_tariff,
            tariff_sensor,
            start_time,
            end_time,
        )

        # Assert
        assert result["energy_kwh"] == 40.0
        # From 10:00 to 11:00: 20 kWh * 0.15 = 3.0
        # From 11:00 to 12:00: 20 kWh * 0.25 = 5.0
        assert result["cost"] == 8.0


async def test_get_energy_at_time_no_data(mock_hass):
    """Test getting energy when no data is available."""
    # Arrange
    entity_id = "sensor.test_energy"
    target_time = datetime(2024, 10, 8, 12, 0)

    with patch(
        "custom_components.elcotra.price_calculations.get_instance"
    ) as mock_get_instance:
        mock_instance = MagicMock()
        # Return empty dict (no data)
        mock_instance.async_add_executor_job = AsyncMock(return_value={})
        mock_get_instance.return_value = mock_instance

        # Act
        result = await get_energy_at_time(mock_hass, [entity_id], target_time)

        # Assert
        assert result == 0.0


async def test_get_energy_at_time_invalid_state(mock_hass):
    """Test getting energy when state is invalid."""
    # Arrange
    entity_id = "sensor.test_energy"
    target_time = datetime(2024, 10, 8, 12, 0)

    mock_state = MagicMock()
    mock_state.state = "unavailable"

    with patch(
        "custom_components.elcotra.price_calculations.get_instance"
    ) as mock_get_instance:
        mock_instance = MagicMock()
        mock_instance.async_add_executor_job = AsyncMock(
            return_value={entity_id: [mock_state]}
        )
        mock_get_instance.return_value = mock_instance

        # Act
        result = await get_energy_at_time(mock_hass, [entity_id], target_time)

        # Assert - should handle gracefully and return 0
        assert result == 0.0


async def test_calculate_period_cost_zero_energy():
    """Test cost calculation when no energy is used."""
    # Arrange
    mock_hass = MagicMock(spec=HomeAssistant)
    energy_sensors = ["sensor.energy"]
    start_time = datetime(2024, 10, 8, 10, 0)
    end_time = datetime(2024, 10, 8, 12, 0)
    fixed_tariff = 0.20

    with patch(
        "custom_components.elcotra.price_calculations.get_energy_at_time",
        new_callable=AsyncMock,
    ) as mock_get_energy:
        # Same energy at start and end (no consumption)
        mock_get_energy.side_effect = [100.0, 100.0]

        # Act
        result = await calculate_period_cost(
            mock_hass,
            energy_sensors,
            TARIFF_TYPE_FIXED,
            fixed_tariff,
            None,
            start_time,
            end_time,
        )

        # Assert
        assert result["energy_kwh"] == 0.0
        assert result["cost"] == 0.0


async def test_get_tariff_for_period():
    """Test getting tariff history for a period."""
    # Arrange
    mock_hass = MagicMock(spec=HomeAssistant)
    tariff_sensor = "sensor.electricity_price"
    start_time = datetime(2024, 10, 8, 10, 0)
    end_time = datetime(2024, 10, 8, 12, 0)

    # Mock tariff states
    mock_state1 = MagicMock()
    mock_state1.state = "0.15"
    mock_state1.last_changed = datetime(2024, 10, 8, 10, 0)

    mock_state2 = MagicMock()
    mock_state2.state = "0.25"
    mock_state2.last_changed = datetime(2024, 10, 8, 11, 0)

    with patch(
        "custom_components.elcotra.price_calculations.get_instance"
    ) as mock_get_instance:
        mock_instance = MagicMock()
        mock_instance.async_add_executor_job = AsyncMock(
            return_value={tariff_sensor: [mock_state1, mock_state2]}
        )
        mock_get_instance.return_value = mock_instance

        # Act
        result = await get_tariff_for_period(
            mock_hass, tariff_sensor, start_time, end_time
        )

        # Assert
        assert len(result) == 2
        assert result[0] == (datetime(2024, 10, 8, 10, 0), 0.15)
        assert result[1] == (datetime(2024, 10, 8, 11, 0), 0.25)
