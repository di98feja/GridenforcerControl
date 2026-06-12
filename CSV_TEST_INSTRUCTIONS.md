# Test Instructions - CSV Import Service (Fas 1)

## Status: Klar för testning! ✅

All kod är implementerad, validerad och redo att testas.

## Vad är implementerat

### Filer skapade/uppdaterade:
- ✅ **csv_importer.py** - CSV nedladdning och parsing
- ✅ **services.py** - Service handler med validering
- ✅ **services.yaml** - Service definition
- ✅ **icons.json** - Service icon
- ✅ **const.py** - Konstanter uppdaterade
- ✅ **strings.json** - Översättningar uppdaterade
- ✅ **__init__.py** - Service registrering
- ✅ **manifest.json** - Dependencies uppdaterade (recorder)
- ✅ **quality_scale.yaml** - Quality scale uppdaterat

### Valideringar passerade:
- ✅ hassfest validation (inga kritiska fel)
- ✅ ruff linting (All checks passed!)
- ✅ mypy type checking (Success!)
- ✅ pylint (inga kritiska fel)

## Hur man testar

### Förutsättningar

1. **Home Assistant måste köra** med gridenforcer_core integrationen laddad
2. **En config entry måste finnas** för integrationen
3. **CSV-filer måste vara tillgängliga** via URL (se format nedan)

### Testscenario 1: Grundläggande import (en fas)

```yaml
service: gridenforcer_core.import_csv_data
data:
  csv_urls:
    l1: "http://192.168.1.100/emeter/0/em_data.csv"
  target_sensors:
    l1: "sensor.shelly_energy_l1"
```

http://192.168.42.226/emeter/0/em_data.csv


**Förväntat resultat:**
- Service returnerar success response
- Offset lagras i config entry
- Statistics importeras till recorder
- Inga fel i loggen

### Testscenario 2: Alla tre faser

```yaml
service: gridenforcer_core.import_csv_data
data:
  csv_urls:
    l1: "http://192.168.1.100/emeter/0/em_data.csv"
    l2: "http://192.168.1.100/emeter/1/em_data.csv"
    l3: "http://192.168.1.100/emeter/2/em_data.csv"
  target_sensors:
    l1: "sensor.shelly_energy_l1"
    l2: "sensor.shelly_energy_l2"
    l3: "sensor.shelly_energy_l3"
```

**Förväntat resultat:**
- Alla tre faser importeras
- Service response visar totalt antal data points
- Offsets lagras för alla faser

### Testscenario 3: Med datumfiltrering

```yaml
service: gridenforcer_core.import_csv_data
data:
  csv_urls:
    l1: "http://192.168.1.100/emeter/0/em_data.csv"
  target_sensors:
    l1: "sensor.shelly_energy_l1"
  import_range:
    start: "2024-01-01T00:00:00"
    end: "2024-12-31T23:59:59"
```

**Förväntat resultat:**
- Endast data inom datumintervallet importeras

### Testscenario 4: Felhantering - Ogiltigt datum

```yaml
service: gridenforcer_core.import_csv_data
data:
  csv_urls:
    l1: "http://192.168.1.100/emeter/0/em_data.csv"
  target_sensors:
    l1: "sensor.shelly_energy_l1"
  import_range:
    start: "2024-12-31T23:59:59"
    end: "2024-01-01T00:00:00"  # Fel: slutdatum före startdatum
```

**Förväntat resultat:**
- ServiceValidationError: "End date must be after start date"

### Testscenario 5: Felhantering - Sensor finns inte

```yaml
service: gridenforcer_core.import_csv_data
data:
  csv_urls:
    l1: "http://192.168.1.100/emeter/0/em_data.csv"
  target_sensors:
    l1: "sensor.does_not_exist"
```

**Förväntat resultat:**
- ServiceValidationError: "Target sensor ... does not exist"

## CSV Format (Shelly)

CSV-filerna måste ha följande format:

```csv
timestamp,energy_wh,power_w
2024-01-01 00:00:00,1234.5,150.2
2024-01-01 00:05:00,1245.8,152.1
2024-01-01 00:10:00,1257.2,153.5
```

### Obligatoriska kolumner:
- `timestamp` - Tidsstämpel (flera format stöds)
- `energy_wh` - Kumulativ energi i Wh

### Valfria kolumner:
- `power_w` - Momentan effekt i W

### Stödda tidsstämpelformat:
- `2024-01-01 00:00:00`
- `2024-01-01T00:00:00`
- `2024-01-01T00:00:00Z`
- `2024-01-01 00:00:00.123` (med millisekunder)

## Loggar att övervaka

Aktivera debug-loggning för gridenforcer_core:

```yaml
logger:
  logs:
    homeassistant.components.gridenforcer_core: debug
```

**Förväntade logmeddelanden:**

```
INFO - Starting CSV import for phases: l1
INFO - Starting CSV import for phase l1 from http://...
INFO - Parsed 1000 data points for phase l1 from 2024-01-01 00:00:00 to 2024-12-31 23:59:59
INFO - Successfully imported 1000 data points for phase l1: 12345.67 kWh total
INFO - Stored energy offsets for phases: l1
INFO - Imported statistics for 1 sensors
INFO - CSV import completed successfully for 1 phases
```

## Service Response

Servicen returnerar:

```json
{
  "success": true,
  "phases_imported": ["l1", "l2", "l3"],
  "total_energy_kwh": 29700.0,
  "cost_offset": 0.0,
  "data_points": 52560
}
```

## Verifiera resultat

### 1. Kontrollera config entry

```python
# Developer Tools > Template
{{ config_entry.data.energy_offsets }}
```

Förväntat:
```json
{
  "l1": {
    "value": 10000.0,
    "imported_at": "2024-10-15T...",
    "source": "http://..."
  }
}
```

### 2. Kontrollera statistics

Gå till Developer Tools > Statistics och sök efter dina sensorer.
Du ska se importerad historik.

### 3. Kontrollera Energy Dashboard

Om sensorerna är kopplade till Energy Dashboard ska den historiska datan
visas där också.

## Kända begränsningar (Fas 1)

- ❌ Energisensorer visar INTE offset ännu (Fas 2)
- ❌ Cost sensors inkluderar INTE importerad data ännu (Fas 2)
- ❌ Historisk kostnadsberäkning är inte implementerad (Fas 2)
- ❌ Ingen UI i config flow (Fas 2)

## Nästa steg (Fas 2)

Efter lyckad testning av Fas 1:

1. Skapa energisensorer med offset-stöd
2. Uppdatera kostnadssensorer
3. Implementera historisk kostnadsberäkning
4. Lägg till config flow UI

## Felsökning

### Problem: "No config entry found"
- Säkerställ att integrationen är konfigurerad via UI först

### Problem: "Failed to download CSV"
- Kontrollera att URL:en är tillgänglig från HA
- Testa URL:en i en webbläsare
- Kontrollera firewall/nätverk

### Problem: "CSV missing required columns"
- Kontrollera att CSV har headers: timestamp, energy_wh
- Kontrollera CSV-formatet (comma-separated)

### Problem: "Could not parse timestamp"
- Kontrollera tidsstämpelformatet i CSV
- Se stödda format ovan

## Support

Vid problem, kontrollera:
1. Home Assistant logs (`homeassistant.log`)
2. Developer Tools > Logs
3. Filtrera på "gridenforcer_core"

