"""Tests for incremental CSV import logic in ElCoTra."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.elcotra.csv_importer import EnergyDataPoint, ShellyCSVImporter
from custom_components.elcotra.csv_services import (
    _async_get_import_baseline,
    _async_get_sum_before,
    _calculate_historical_cost_from_import,
)
import pytest

from homeassistant.core import HomeAssistant


@pytest.fixture
def mock_hass():
    """Create a mock HomeAssistant instance."""
    return MagicMock(spec=HomeAssistant)


def _mock_recorder(rows_by_id):
    """Create a mocked recorder instance whose executor returns canned rows."""
    instance = MagicMock()
    instance.async_add_executor_job = AsyncMock(return_value=rows_by_id)
    return instance


async def test_baseline_no_statistics(mock_hass):
    """Test baseline when the sensor has no recorded statistics."""
    with patch(
        "custom_components.elcotra.csv_services.get_instance",
        return_value=_mock_recorder({}),
    ):
        high_water, seed = await _async_get_import_baseline(
            mock_hass, "sensor.energy_l1"
        )

    assert high_water is None
    assert seed == 0.0


async def test_baseline_returns_last_hour_and_previous_sum(mock_hass):
    """Test baseline with two recorded hours (newest first)."""
    last_hour = datetime(2024, 10, 8, 14, 0, tzinfo=UTC)
    rows = {
        "sensor.energy_l1": [
            {"start": last_hour.timestamp(), "sum": 120.0},
            {
                "start": datetime(2024, 10, 8, 13, 0, tzinfo=UTC).timestamp(),
                "sum": 100.0,
            },
        ]
    }

    with patch(
        "custom_components.elcotra.csv_services.get_instance",
        return_value=_mock_recorder(rows),
    ):
        high_water, seed = await _async_get_import_baseline(
            mock_hass, "sensor.energy_l1"
        )

    assert high_water == last_hour
    # Seed is the sum BEFORE the last hour, so the last (possibly partial)
    # hour can be rebuilt from CSV rows
    assert seed == 100.0


async def test_baseline_single_statistic_seeds_zero(mock_hass):
    """Test baseline when only one statistics hour exists."""
    last_hour = datetime(2024, 10, 8, 14, 0, tzinfo=UTC)
    rows = {"sensor.energy_l1": [{"start": last_hour.timestamp(), "sum": 5.0}]}

    with patch(
        "custom_components.elcotra.csv_services.get_instance",
        return_value=_mock_recorder(rows),
    ):
        high_water, seed = await _async_get_import_baseline(
            mock_hass, "sensor.energy_l1"
        )

    assert high_water == last_hour
    assert seed == 0.0


async def test_sum_before_picks_newest_row_before_cutoff(mock_hass):
    """Test sum lookup returns the newest sum strictly before the cutoff."""
    rows = {
        "sensor.cost": [
            {
                "start": datetime(2024, 10, 8, 14, 0, tzinfo=UTC).timestamp(),
                "sum": 80.0,
            },
            {
                "start": datetime(2024, 10, 8, 13, 0, tzinfo=UTC).timestamp(),
                "sum": 70.0,
            },
        ]
    }

    with patch(
        "custom_components.elcotra.csv_services.get_instance",
        return_value=_mock_recorder(rows),
    ):
        # Cutoff after both rows: newest wins
        assert (
            await _async_get_sum_before(
                mock_hass, "sensor.cost", datetime(2024, 10, 8, 15, 0, tzinfo=UTC)
            )
            == 80.0
        )
        # Cutoff at the newest row: it is excluded, previous row wins
        assert (
            await _async_get_sum_before(
                mock_hass, "sensor.cost", datetime(2024, 10, 8, 14, 0, tzinfo=UTC)
            )
            == 70.0
        )
        # Cutoff before everything: no baseline
        assert (
            await _async_get_sum_before(
                mock_hass, "sensor.cost", datetime(2024, 10, 8, 12, 0, tzinfo=UTC)
            )
            == 0.0
        )


def _make_entry(data):
    """Create a mock config entry with the given data."""
    entry = MagicMock()
    entry.data = data
    return entry


async def test_cost_calculation_fixed_tariff_seeded(mock_hass):
    """Test cost calculation continues the sum and uses fixed tariff."""
    hour1 = datetime(2024, 10, 8, 10, 0, tzinfo=UTC)
    hour2 = datetime(2024, 10, 8, 11, 0, tzinfo=UTC)

    hourly_deltas = {
        "sensor.energy_l1": {hour1: 10.0, hour2: 5.0},
        "sensor.energy_l2": {hour1: 2.0},
    }

    mock_hass.config_entries.async_entries.return_value = [
        _make_entry({"tariff_type": "fixed", "fixed_tariff": 0.5})
    ]

    with patch(
        "custom_components.elcotra.csv_services._async_get_sum_before",
        new_callable=AsyncMock,
        return_value=100.0,
    ):
        stats, total = await _calculate_historical_cost_from_import(
            mock_hass, hourly_deltas, "sensor.cost", True
        )

    # Hour 1: 12 kWh * 0.5 = 6.0, hour 2: 5 kWh * 0.5 = 2.5, seeded from 100.0
    assert len(stats) == 2
    assert stats[0]["start"] == hour1
    assert stats[0]["sum"] == 106.0
    assert stats[1]["sum"] == 108.5
    assert total == 108.5


async def test_cost_calculation_tariff_merge_pass(mock_hass):
    """Test the single-pass tariff lookup gives each hour the right price."""
    hours = [datetime(2024, 10, 8, h, 0, tzinfo=UTC) for h in (10, 11, 12, 13)]
    hourly_deltas = {"sensor.energy_l1": dict.fromkeys(hours, 10.0)}

    mock_hass.config_entries.async_entries.return_value = [
        _make_entry(
            {
                "tariff_type": "sensor",
                "fixed_tariff": 1.0,
                "tariff_sensor": "sensor.price",
            }
        )
    ]

    # Tariff statistics: 0.2 from 11:00, 0.4 from 13:00 (nothing before 11:00)
    tariff_rows = {
        "sensor.price": [
            {"start": hours[1], "mean": 0.2},
            {"start": hours[3], "mean": 0.4},
        ]
    }

    with (
        patch(
            "custom_components.elcotra.csv_services.get_instance",
            return_value=_mock_recorder(tariff_rows),
        ),
        patch(
            "custom_components.elcotra.csv_services._async_get_sum_before",
            new_callable=AsyncMock,
            return_value=0.0,
        ),
    ):
        stats, total = await _calculate_historical_cost_from_import(
            mock_hass, hourly_deltas, "sensor.cost", True
        )

    # 10:00 has no tariff yet -> fixed fallback 1.0 -> 10.0
    # 11:00 and 12:00 -> 0.2 -> 2.0 each
    # 13:00 -> 0.4 -> 4.0
    sums = [s["sum"] for s in stats]
    assert sums == [10.0, 12.0, 14.0, 18.0]
    assert total == 18.0


async def test_cost_calculation_not_seeded_on_full_reimport(mock_hass):
    """Test that full re-imports rebuild the cost sum from zero."""
    hour1 = datetime(2024, 10, 8, 10, 0, tzinfo=UTC)
    hourly_deltas = {"sensor.energy_l1": {hour1: 10.0}}

    mock_hass.config_entries.async_entries.return_value = [
        _make_entry({"tariff_type": "fixed", "fixed_tariff": 0.5})
    ]

    with patch(
        "custom_components.elcotra.csv_services._async_get_sum_before",
        new_callable=AsyncMock,
    ) as mock_sum_before:
        _stats, total = await _calculate_historical_cost_from_import(
            mock_hass, hourly_deltas, "sensor.cost", False
        )

    mock_sum_before.assert_not_called()
    assert total == 5.0


async def test_import_from_url_empty_after_filter_returns_empty_result(mock_hass):
    """Test that filtering out all rows yields an empty result, not an error."""
    importer = ShellyCSVImporter.__new__(ShellyCSVImporter)
    importer.hass = mock_hass

    old_point = EnergyDataPoint(
        timestamp=datetime(2024, 10, 8, 10, 30, tzinfo=UTC), energy_wh=100.0
    )

    async def run_in_executor(func, *args):
        return func(*args)

    mock_hass.async_add_executor_job = AsyncMock(side_effect=run_in_executor)

    with (
        patch.object(importer, "download_csv", AsyncMock(return_value="csv")),
        patch.object(importer, "parse_csv", return_value=[old_point]),
    ):
        result = await importer.import_from_url(
            "http://example/em.csv",
            "l1",
            start_date=datetime(2024, 10, 9, 0, 0, tzinfo=UTC),
        )

    assert result.data_points == []
    assert result.total_energy_kwh == 0.0


async def test_import_from_url_parses_in_executor(mock_hass):
    """Test that CSV parsing is dispatched to the executor."""
    importer = ShellyCSVImporter.__new__(ShellyCSVImporter)
    importer.hass = mock_hass

    point = EnergyDataPoint(
        timestamp=datetime(2024, 10, 8, 10, 30, tzinfo=UTC), energy_wh=100.0
    )
    mock_hass.async_add_executor_job = AsyncMock(return_value=[point])

    with patch.object(importer, "download_csv", AsyncMock(return_value="csv")):
        result = await importer.import_from_url("http://example/em.csv", "l1")

    mock_hass.async_add_executor_job.assert_awaited_once_with(
        importer.parse_csv, "csv", "l1"
    )
    assert result.data_points == [point]
    assert result.total_energy_kwh == 0.1
