# Historical Data Import - Implementation Summary

## Overview
The historical data import service has been successfully implemented for the ElCoTra integration. This service allows users to import historical electricity cost calculations retroactively.

## Implementation Details

### Files Modified

1. **`config/custom_components/elcotra/__init__.py`**
   - Added service registration for `elcotra.import_historical_costs`
   - Implemented service handler with validation and error handling
   - Added persistent notifications for user feedback
   - Service validates date ranges and provides progress updates

2. **`config/custom_components/elcotra/price_calculations.py`**
   - Added `import_historical_statistics()` function
   - Implements 15-minute interval calculations matching the coordinator
   - Handles tariff fallback when historical price data is unavailable
   - Uses Home Assistant Statistics API for data import
   - Includes comprehensive error handling

3. **`config/custom_components/elcotra/services.yaml`**
   - Service definition with proper field descriptions
   - Already created in previous work

## Service Usage

### Service Call
```yaml
service: elcotra.import_historical_costs
data:
  start_date: "2024-09-01"
  end_date: "2024-10-10"  # Optional, defaults to today
  fallback_tariff: 1.2     # Optional, defaults to config fixed_tariff
```

### Parameters

- **start_date** (required): Start date for historical import (YYYY-MM-DD)
- **end_date** (optional): End date for import, defaults to current date
- **fallback_tariff** (optional): Tariff to use when historical price data is unavailable

## Features Implemented

### ✅ Core Functionality
- 15-minute interval calculations (matching coordinator behavior)
- Automatic tariff fallback when price sensor data is missing
- Support for both fixed and sensor-based tariffs
- Progress logging every 100 entries
- Statistics import using Home Assistant recorder API

### ✅ Error Handling
- Validates date range (end_date must be after start_date)
- Checks for integration configuration existence
- Handles missing energy sensor data gracefully
- Handles missing tariff sensor data with fallback
- Specific exception types (ValueError, TypeError, KeyError)

### ✅ User Feedback
- Persistent notification when import starts
- Persistent notification on completion with statistics
- Persistent notification on errors
- Detailed logging at appropriate levels

### ✅ Code Quality
- All ruff linting checks pass
- Proper import sorting
- Type hints throughout
- Comprehensive docstrings
- Follows Home Assistant coding standards

## How It Works

### Calculation Process

1. **Initialization**
   - Validates date range
   - Converts dates to datetime objects with local timezone
   - Gets baseline energy reading at start_date

2. **15-Minute Intervals**
   - Loops through 15-minute intervals from start to end date
   - For each interval:
     - Fetches energy readings at period start and end
     - Calculates energy consumed in period
     - Determines tariff (from sensor history or fallback)
     - Calculates cost: `period_energy × period_tariff`
     - Accumulates total cost

3. **Statistics Import**
   - Creates statistics metadata:
     - source: "elcotra"
     - statistic_id: `sensor.{entry_id}_cost`
     - unit_of_measurement: Currency from config
     - has_sum: True (for TOTAL_INCREASING)
   - Imports all accumulated cost values with timestamps
   - Uses `async_import_statistics()` API

### Tariff Fallback Logic

```
if tariff_type == TARIFF_TYPE_FIXED:
    use fixed_tariff
elif tariff_sensor exists:
    try:
        get tariff from sensor history
        if no data:
            use fallback_tariff (or fixed_tariff if not provided)
    except error:
        use fallback_tariff
else:
    use fallback_tariff
```

## Testing Recommendations

### Manual Testing Steps

1. **Basic Import Test**
   ```yaml
   service: elcotra.import_historical_costs
   data:
     start_date: "2024-10-01"
     end_date: "2024-10-05"
   ```
   - Verify notification appears
   - Check logs for progress messages
   - Verify completion notification with statistics

2. **Fallback Tariff Test**
   ```yaml
   service: elcotra.import_historical_costs
   data:
     start_date: "2024-09-01"  # Before Nordpool installation
     end_date: "2024-09-15"
     fallback_tariff: 1.5
   ```
   - Should use fallback_tariff when price sensor data missing

3. **Error Handling Test**
   ```yaml
   service: elcotra.import_historical_costs
   data:
     start_date: "2024-10-10"
     end_date: "2024-10-01"  # Invalid: end before start
   ```
   - Should show error notification

4. **Long Range Test**
   ```yaml
   service: elcotra.import_historical_costs
   data:
     start_date: "2024-01-01"
     end_date: "2024-10-10"
   ```
   - Verify performance with many intervals (1000+ entries)
   - Check progress logging every 100 entries

### Unit Testing

A test file should be created: `tests/custom_components/elcotra/test_historical_import.py`

Test cases to implement:
- Test basic import with fixed tariff
- Test import with sensor-based tariff
- Test fallback tariff usage
- Test date validation
- Test error handling for missing energy data
- Test statistics metadata creation

Example test structure:
```python
async def test_import_historical_statistics_fixed_tariff():
    """Test importing historical statistics with fixed tariff."""
    # Mock get_energy_at_time to return predictable values
    # Mock async_import_statistics
    # Call import_historical_statistics
    # Assert correct number of entries created
    # Assert correct total cost calculation
```

## Known Limitations

1. **Single Entry Support**: Currently uses first config entry if multiple exist
   - Future: Add config entry selector to service

2. **No Progress Updates**: For very long imports, user only sees start/end notifications
   - Future: Consider periodic progress notifications or progress entity

3. **No Duplicate Handling**: Statistics API behavior with existing data needs verification
   - Future: Add option to skip/overwrite existing statistics

4. **Gap Handling**: Missing energy data gaps are logged but not handled specially
   - Current: Logs warning and continues
   - Future: Could interpolate or provide user option

## Future Enhancements

### Priority 1
- [ ] Add unit tests for import_historical_statistics function
- [ ] Test with real Shelly and Nordpool data
- [ ] Verify Statistics API behavior with existing data

### Priority 2
- [ ] Add config entry selector to service
- [ ] Add option to overwrite vs. skip existing statistics
- [ ] Progress entity for long-running imports

### Priority 3
- [ ] Support for multiple energy sensors with individual statistics
- [ ] Export functionality to CSV/JSON
- [ ] Visualization of imported data in UI

## Answers to Original Questions

### 1. How to handle multiple config entries?
**Current**: Uses first entry found
**Future**: Add optional `config_entry_id` parameter to service

### 2. Should we give progress feedback?
**Current**: Persistent notifications at start/end + logging every 100 entries
**Future**: Could add progress entity or periodic notifications

### 3. What happens if statistics already exist?
**Current**: Statistics API will handle duplicates (needs testing)
**Future**: Add explicit overwrite/skip option

### 4. How to handle gaps in energy data?
**Current**: Logs warning and skips that period
**Future**: Could add interpolation option or better gap detection

## Verification Checklist

Before deploying to production:

- [x] Code passes all linting checks (ruff)
- [x] Proper error handling implemented
- [x] User feedback via notifications
- [x] Logging at appropriate levels
- [ ] Unit tests created and passing
- [ ] Manual testing with real data
- [ ] Statistics visualization verified in Home Assistant UI
- [ ] Performance tested with large date ranges
- [ ] Documentation updated

## Developer Notes

### Important Constants
- `UPDATE_INTERVAL_SECONDS = 900` (15 minutes)
- Matches coordinator update frequency
- Statistics use same interval for consistency

### Statistics API Usage
```python
metadata = {
    "source": "elcotra",
    "statistic_id": f"sensor.{entry_id}_cost",
    "unit_of_measurement": currency,
    "has_mean": False,
    "has_sum": True,
}

statistics = [
    {
        "start": timestamp,
        "state": accumulated_cost,
        "sum": accumulated_cost,
    },
    # ... more entries
]

async_import_statistics(hass, metadata, statistics)
```

### Debugging Tips
- Enable debug logging: `logger: custom_components.elcotra: debug`
- Check logs for "Starting historical import" messages
- Progress logged every 100 entries
- Warnings logged for missing data periods

## Conclusion

The historical data import service is fully implemented and ready for testing. The implementation follows Home Assistant best practices, includes comprehensive error handling, and provides good user feedback through persistent notifications.

Next step is to test with real data and verify the Statistics API integration works correctly with the Home Assistant recorder database.
