# CSV Import för ElCoTra - Testinstruktioner

## Status: ✅ Klar för testning!

CSV-import funktionaliteten är nu implementerad i **elcotra** integrationen (inte gridenforcer_core).

## Vad är implementerat

### Nya filer i `config/custom_components/elcotra/`:
- ✅ **csv_importer.py** - CSV nedladdning och parsing från URL
- ✅ **csv_services.py** - Service handler för CSV-import
- ✅ **const.py** - Uppdaterad med CSV-konstanter
- ✅ **__init__.py** - Uppdaterad för att registrera CSV-service
- ✅ **services.yaml** - Uppdaterad med import_csv_data definition
- ✅ **strings.json** - Uppdaterad med översättningar
- ✅ **manifest.json** - Uppdaterad med recorder dependency

## Användning

### Service: elcotra.import_csv_data

```yaml
service: elcotra.import_csv_data
data:
  csv_urls:
    l1: "http://192.168.1.100/emeter/0/em_data.csv"
    l2: "http://192.168.1.100/emeter/1/em_data.csv"
    l3: "http://192.168.1.100/emeter/2/em_data.csv"
  target_sensors:
    l1: "sensor.shelly_em_energy_phase_a"
    l2: "sensor.shelly_em_energy_phase_b"
    l3: "sensor.shelly_em_energy_phase_c"
```

### Med datumfiltrering:

```yaml
service: elcotra.import_csv_data
data:
  csv_urls:
    l1: "http://192.168.1.100/emeter/0/em_data.csv"
  target_sensors:
    l1: "sensor.shelly_em_energy_phase_a"
  import_range:
    start: "2024-01-01T00:00:00"
    end: "2024-12-31T23:59:59"
  options:
    apply_to_cost_sensors: true
    recalculate_statistics: true
```

## CSV Format (Shelly)

Förväntad CSV-struktur:

```csv
timestamp,energy_wh,power_w
2024-01-01 00:00:00,1234.5,150.2
2024-01-01 00:05:00,1245.8,152.1
2024-01-01 00:10:00,1257.2,153.5
```

### Obligatoriska kolumner:
- `timestamp` - Tidsstämpel
- `energy_wh` - Kumulativ energi i Wh

### Valfria kolumner:
- `power_w` - Momentan effekt i W

### Stödda tidsstämpelformat:
- `2024-01-01 00:00:00`
- `2024-01-01T00:00:00`
- `2024-01-01T00:00:00Z`
- Med millisekunder: `2024-01-01T00:00:00.123`

## Testscenarier

### 1. Grundläggande test (en fas)

```yaml
service: elcotra.import_csv_data
data:
  csv_urls:
    l1: "http://shelly.local/emeter/0/em_data.csv"
  target_sensors:
    l1: "sensor.shelly_em_energy_phase_a"
```

**Förväntat:**
- Service returnerar success
- Offset lagras i config entry
- Statistics importeras
- Loggar visar antal importerade datapunkter

### 2. Alla tre faser

```yaml
service: elcotra.import_csv_data
data:
  csv_urls:
    l1: "http://shelly.local/emeter/0/em_data.csv"
    l2: "http://shelly.local/emeter/1/em_data.csv"
    l3: "http://shelly.local/emeter/2/em_data.csv"
  target_sensors:
    l1: "sensor.shelly_em_energy_phase_a"
    l2: "sensor.shelly_em_energy_phase_b"
    l3: "sensor.shelly_em_energy_phase_c"
```

**Förväntat:**
- Alla tre faser importeras
- Service response visar totalt för alla faser
- Offsets för L1, L2, L3 lagras separat

### 3. Felhantering - Sensor finns inte

```yaml
service: elcotra.import_csv_data
data:
  csv_urls:
    l1: "http://shelly.local/emeter/0/em_data.csv"
  target_sensors:
    l1: "sensor.does_not_exist"
```

**Förväntat:**
- ServiceValidationError
- Tydligt felmeddelande om att sensor inte finns

### 4. Felhantering - Ogiltigt datum

```yaml
service: elcotra.import_csv_data
data:
  csv_urls:
    l1: "http://shelly.local/emeter/0/em_data.csv"
  target_sensors:
    l1: "sensor.shelly_em_energy_phase_a"
  import_range:
    start: "2024-12-31T23:59:59"
    end: "2024-01-01T00:00:00"  # Fel ordning!
```

**Förväntat:**
- ServiceValidationError: "End date must be after start date"

## Loggar

Aktivera debug-loggning:

```yaml
logger:
  logs:
    custom_components.elcotra: debug
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

```json
{
  "success": true,
  "phases_imported": ["l1", "l2", "l3"],
  "total_energy_kwh": 29700.0,
  "cost_offset": 0.0,
  "data_points": 52560
}
```

## Verifiera Resultat

### 1. Kontrollera offset i config entry

```yaml
# Developer Tools > Template
{% set entry_id = "din_entry_id_här" %}
{{ states.sensor | selectattr('entity_id', 'search', 'elcotra') | map(attribute='entity_id') | list }}
```

### 2. Kontrollera statistics

Gå till:
- Developer Tools > Statistics
- Sök efter dina energy sensorer
- Du ska se historisk data från importen

### 3. Kontrollera Energy Dashboard

Om sensorerna är kopplade till Energy Dashboard:
- Öppna Energy Dashboard
- Välj datumintervall som täcker importerad data
- Historisk energi ska visas

## Hur det fungerar

1. **CSV nedladdning**: Via URL från Shelly-enheten
2. **Parsing**: Läser timestamp och energy_wh kolumner
3. **Offset beräkning**: Summerar total energi från CSV
4. **Statistics import**: Skriver till HA recorder database
5. **Offset lagring**: Sparas i config entry för framtida användning

## Integration med ElCoTra

- ✅ Offsets lagras i config entry
- ✅ Statistics importeras för energisensorer
- ⏳ Cost sensor uppdatering (Fas 2)
- ⏳ Historisk kostnadsberäkning (Fas 2)

## Nästa Steg (Fas 2)

Efter lyckad testning:

1. **Uppdatera cost sensor** att inkludera offset i beräkning
2. **Implementera historisk kostnadsberäkning** med spotpriser
3. **UI för import** i config flow

## Felsökning

### "No config entry found"
- Kontrollera att elcotra är konfigurerad via UI

### "Failed to download CSV"
- Testa URL:en i webbläsare
- Kontrollera nätverksanslutning från HA till Shelly
- Kontrollera att Shelly har CSV-export aktiverat

### "CSV missing required columns"
- Kontrollera att CSV har headers: timestamp, energy_wh
- Öppna CSV i textredigerare och verifiera format

### "Could not parse timestamp"
- Kontrollera tidsstämpelformatet i CSV
- Se stödda format ovan

## Service Jämförelse

ElCoTra har nu **två** import-services:

### 1. import_historical_costs
- Beräknar kostnader retroaktivt
- Använder befintlig HA history för energi
- Kräver att energisensorer redan har historik

### 2. import_csv_data (NY!)
- Importerar energidata från CSV
- Laddar ner från Shelly via URL
- Skapar historik där ingen fanns
- Bas för framtida kostnadsberäkningar

## Tips

- Börja med en fas (l1) för att testa
- Använd ett kortare datumintervall första gången
- Kontrollera logs under import
- Verifiera statistics efter import
- Expandera sedan till alla faser

## Exempel på komplett användning

```yaml
# Steg 1: Importera energidata från Shelly CSV
service: elcotra.import_csv_data
data:
  csv_urls:
    l1: "http://192.168.1.100/emeter/0/em_data.csv"
    l2: "http://192.168.1.100/emeter/1/em_data.csv"
    l3: "http://192.168.1.100/emeter/2/em_data.csv"
  target_sensors:
    l1: "sensor.shelly_em_energy_phase_a"
    l2: "sensor.shelly_em_energy_phase_b"
    l3: "sensor.shelly_em_energy_phase_c"

# Steg 2 (Fas 2): Beräkna historiska kostnader baserat på importerad data
# (Kommer i nästa version)
```

Lycka till med testningen! 🚀
