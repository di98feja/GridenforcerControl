"""CSV importer for historical energy data from Shelly devices."""

from __future__ import annotations

import asyncio
import csv
from dataclasses import dataclass
from datetime import datetime
from io import StringIO
import logging

import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import dt as dt_util

_LOGGER = logging.getLogger(__name__)


@dataclass
class EnergyDataPoint:
    """Represents a single energy data point from CSV."""

    timestamp: datetime
    energy_wh: float
    power_w: float | None = None


@dataclass
class ImportResult:
    """Result of CSV import operation."""

    phase: str
    data_points: list[EnergyDataPoint]
    total_energy_kwh: float
    start_date: datetime | None
    end_date: datetime | None
    source_url: str


class CSVImportError(HomeAssistantError):
    """Exception raised when CSV import fails."""


class CSVParseError(CSVImportError):
    """Exception raised when CSV parsing fails."""


class CSVNotReadyError(CSVImportError):
    """Exception raised when CSV file indicates data is not ready."""


class CSVDownloadError(CSVImportError):
    """Exception raised when CSV download fails."""


class ShellyCSVImporter:
    """Handles downloading and parsing Shelly CSV energy data."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the CSV importer."""
        self.hass = hass
        self._session = async_get_clientsession(hass)

    async def download_csv(self, url: str) -> str:
        """Download CSV file from URL.

        Args:
            url: URL to the CSV file

        Returns:
            CSV content as string

        Raises:
            CSVDownloadError: If download fails
        """
        try:
            async with self._session.get(
                url, timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                if response.status != 200:
                    raise CSVDownloadError(
                        f"Failed to download CSV from {url}: HTTP {response.status}"
                    )
                content = await response.text()
                if not content:
                    raise CSVDownloadError(f"Empty CSV file downloaded from {url}")
                return content
        except aiohttp.ClientError as err:
            raise CSVDownloadError(
                f"Network error downloading CSV from {url}: {err}"
            ) from err
        except TimeoutError as err:
            raise CSVDownloadError(f"Timeout downloading CSV from {url}") from err

    def parse_csv(self, csv_content: str, phase: str) -> list[EnergyDataPoint]:
        """Parse CSV content into energy data points.

        Expected CSV format (Shelly):
        timestamp,energy_wh,power_w
        2024-01-01 00:00:00,1234.5,150.2
        2024-01-01 00:05:00,1245.8,152.1

        Args:
            csv_content: CSV file content
            phase: Phase identifier (l1, l2, l3)

        Returns:
            List of energy data points

        Raises:
            CSVParseError: If parsing fails
        """
        data_points: list[EnergyDataPoint] = []

        try:
            csv_file = StringIO(csv_content)
            reader = csv.DictReader(csv_file)

            if not reader.fieldnames:
                raise CSVParseError("CSV file has no headers")

            if reader.fieldnames[0] == "Another file transfer is in progress!":
                raise CSVNotReadyError(
                    "CSV file indicates another transfer is in progress"
                )

            # Detect column mapping for Shelly format
            timestamp_col, energy_col, power_col = self._detect_columns(
                reader.fieldnames, phase
            )

            line_number = 1
            for row in reader:
                line_number += 1
                try:
                    # Parse timestamp (support multiple formats)
                    timestamp_str = row[timestamp_col].strip()
                    timestamp = self._parse_timestamp(timestamp_str)

                    # Parse energy (in Wh)
                    energy_wh = float(row[energy_col])

                    # Parse power if available (optional)
                    power_w = None
                    if power_col and row.get(power_col):
                        power_w = float(row[power_col])

                    data_points.append(
                        EnergyDataPoint(
                            timestamp=timestamp,
                            energy_wh=energy_wh,
                            power_w=power_w,
                        )
                    )

                except (ValueError, KeyError) as err:
                    _LOGGER.warning(
                        "Skipping invalid row %d in phase %s CSV: %s",
                        line_number,
                        phase,
                        err,
                    )
                    continue

            if not data_points:
                raise CSVParseError(
                    f"No valid data points found in CSV for phase {phase}"
                )

            # Sort by timestamp
            data_points.sort(key=lambda x: x.timestamp)

            _LOGGER.info(
                "Parsed %d data points for phase %s from %s to %s",
                len(data_points),
                phase,
                data_points[0].timestamp,
                data_points[-1].timestamp,
            )

        except csv.Error as err:
            raise CSVParseError(f"CSV parsing error: {err}") from err
        else:
            return data_points

    def _detect_columns(
        self, fieldnames: list[str], phase: str
    ) -> tuple[str, str, str | None]:
        """Detect column names in CSV file.

        Supports various Shelly CSV formats.

        Args:
            fieldnames: List of column names from CSV
            phase: Phase identifier for logging

        Returns:
            Tuple of (timestamp_column, energy_column, power_column)

        Raises:
            CSVParseError: If required columns cannot be found
        """
        timestamp_col = None
        energy_col = None
        power_col = None

        # Detect timestamp column
        for col in fieldnames:
            col_lower = col.lower()
            if any(
                keyword in col_lower
                for keyword in ["date", "time", "timestamp", "datetime"]
            ):
                timestamp_col = col
                break

        # Detect energy column (look for "active energy" or "energy_wh")
        for col in fieldnames:
            col_lower = col.lower()
            if "active energy" in col_lower or "energy_wh" in col_lower:
                energy_col = col
                break

        # Detect power column (optional)
        for col in fieldnames:
            col_lower = col.lower()
            if "power" in col_lower and "active" in col_lower:
                power_col = col
                break

        if not timestamp_col or not energy_col:
            raise CSVParseError(
                f"Could not detect required columns in CSV for phase {phase}. "
                f"Available columns: {fieldnames}. "
                f"Detected: timestamp={timestamp_col}, energy={energy_col}"
            )

        _LOGGER.debug(
            "Detected columns for phase %s: timestamp='%s', energy='%s', power='%s'",
            phase,
            timestamp_col,
            energy_col,
            power_col,
        )

        return timestamp_col, energy_col, power_col

    def _parse_timestamp(self, timestamp_str: str) -> datetime:
        """Parse timestamp from various formats.

        Args:
            timestamp_str: Timestamp string

        Returns:
            Parsed datetime object

        Raises:
            ValueError: If timestamp cannot be parsed
        """
        # Try common formats
        formats = [
            "%Y-%m-%d %H:%M:%S",  # 2024-01-01 00:00:00
            "%Y-%m-%d %H:%M",  # 2024-01-01 00:00 (Shelly format without seconds)
            "%Y-%m-%dT%H:%M:%S",  # 2024-01-01T00:00:00
            "%Y-%m-%dT%H:%M",  # 2024-01-01T00:00
            "%Y-%m-%d %H:%M:%S.%f",  # With milliseconds
            "%Y-%m-%dT%H:%M:%S.%f",  # ISO with milliseconds
            "%Y-%m-%dT%H:%M:%SZ",  # UTC ISO format
        ]

        for fmt in formats:
            try:
                naive_dt = datetime.strptime(timestamp_str, fmt)
                # Convert naive datetime to timezone-aware (use Home Assistant's timezone)
                return dt_util.as_local(naive_dt)
            except ValueError:
                continue

        raise ValueError(f"Could not parse timestamp: {timestamp_str}")

    async def import_from_url(
        self,
        url: str,
        phase: str,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> ImportResult:
        """Import energy data from CSV URL.

        Args:
            url: URL to CSV file
            phase: Phase identifier (l1, l2, l3)
            start_date: Optional start date filter
            end_date: Optional end date filter

        Returns:
            Import result with parsed data

        Raises:
            CSVImportError: If import fails
        """
        _LOGGER.info("Starting CSV import for phase %s from %s", phase, url)

        # Download CSV
        csv_content = await self.download_csv(url)

        # Parse CSV in the executor - parsing the full history is CPU-bound
        # and must not block the event loop
        data_points = await self.hass.async_add_executor_job(
            self.parse_csv, csv_content, phase
        )

        # Filter by date range if specified
        if start_date or end_date:
            data_points = [
                dp
                for dp in data_points
                if (not start_date or dp.timestamp >= start_date)
                and (not end_date or dp.timestamp <= end_date)
            ]

        if not data_points:
            # Normal case for incremental imports: nothing new since last run
            _LOGGER.info(
                "No data points for phase %s in range %s - %s, nothing to import",
                phase,
                start_date,
                end_date,
            )
            return ImportResult(
                phase=phase,
                data_points=[],
                total_energy_kwh=0.0,
                start_date=None,
                end_date=None,
                source_url=url,
            )

        # Calculate total energy in kWh
        # Shelly reports energy per minute, so sum all values
        total_energy_wh = sum(dp.energy_wh for dp in data_points)
        total_energy_kwh = total_energy_wh / 1000.0

        _LOGGER.debug(
            "Phase %s: Summed %.2f Wh from %d readings = %.2f kWh",
            phase,
            total_energy_wh,
            len(data_points),
            total_energy_kwh,
        )

        result = ImportResult(
            phase=phase,
            data_points=data_points,
            total_energy_kwh=total_energy_kwh,
            start_date=data_points[0].timestamp,
            end_date=data_points[-1].timestamp,
            source_url=url,
        )

        _LOGGER.info(
            "Successfully imported %d data points for phase %s: %.2f kWh total",
            len(data_points),
            phase,
            total_energy_kwh,
        )

        return result

    async def import_multiple_phases(
        self,
        urls: dict[str, str],
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        start_dates: dict[str, datetime] | None = None,
    ) -> dict[str, ImportResult]:
        """Import CSV data for multiple phases.

        Args:
            urls: Dictionary mapping phase names to CSV URLs
                  Example: {"l1": "http://...", "l2": "http://...", "l3": "http://..."}
            start_date: Optional start date filter
            end_date: Optional end date filter
            start_dates: Optional per-phase start date filters, overriding
                         start_date for the phases present in the dict

        Returns:
            Dictionary mapping phase names to import results

        Raises:
            CSVImportError: If any import fails
        """
        results: dict[str, ImportResult] = {}

        for phase, url in urls.items():
            phase_start = (start_dates or {}).get(phase, start_date)
            try:
                for retries in range(10):
                    try:
                        result = await self.import_from_url(
                            url, phase, phase_start, end_date
                        )
                        results[phase] = result
                        break
                    except CSVNotReadyError as not_ready_err:
                        _LOGGER.warning(
                            "Phase %s CSV not ready (attempt %d/10): %s",
                            phase,
                            retries + 1,
                            not_ready_err,
                        )
                        await asyncio.sleep(0.1 * (retries + 1))  # Exponential backoff
                        continue
            except CSVImportError as err:
                _LOGGER.error("Failed to import phase %s: %s", phase, err)
                raise

        _LOGGER.info(
            "Successfully imported data for %d phases: %s",
            len(results),
            ", ".join(results.keys()),
        )

        return results
