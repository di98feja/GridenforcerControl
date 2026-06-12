# Historical Energy Data Import - CSV från Shelly

## Översikt

Denna implementation tillåter import av historisk energidata från Shelly CSV-filer via URL:er direkt in i Home Assistant. Data integreras sömlöst med energi- och kostnadssensorer.

## Arkitektur

```
CSV-filer (Shelly via URL) → Nedladdning → Parsing → Statistics DB + Offsets
                                                              ↓
                                                  Energisensorer (med offset)
                                                              ↓
                                                  Kostnadssensorer (beräknade)
```

## Funktioner

✅ **URL-baserad nedladdning** - Ange bara URL:er, ingen filuppladdning
✅ **Per-fas import** - Stöd för L1, L2, L3 faser separat
✅ **Statistics-integration** - Importerar till HA långtidsstatistik
✅ **Offset-hantering** - Lagrar historiska totaler för sömlös visning
✅ **Datumfiltrering** - Importera endast specifika tidsperioder
✅ **Kostnadsberäkning** - Automatisk historisk kostnadsberäkning (framtida)

## Användning

### 1. Service Call Exempel

```yaml
service: gridenforcer_core.import_csv_data
data:
  csv_urls:
    l1: "http://192.168.1.100/emeter/0/em_data.csv"
    l2: "http://192.168.1.100/emeter/1/em_data.csv"
    l3: "http://192.168.1.100/emeter/2/em_data.csv"
  target_sensors:
    l1: "sensor.gridenforcer_energy_l1"
    l2: "sensor.gridenforcer_energy_l2"
    l3: "sensor.gridenforcer_energy_l3"
  import_range:
    start: "2024-01-01T00:00:00"
    end: "2024-12-31T23:59:59"
  options:
    apply_to_cost_sensors: true
    recalculate_statistics: true
    backup_existing: true
```

### 2. Developer Tools Exempel

```yaml
service: gridenforcer_core.import_csv_data
data:
  csv_urls:
    l1: "http://shelly.local/emeter/0/em_data.csv"
  target_sensors:
    l1: "sensor.shelly_energy_l1"
```

## Förväntat CSV-format (Shelly)

```csv
timestamp,energy_wh,power_w
2024-01-01 00:00:00,1234.5,150.2
2024-01-01 00:05:00,1245.8,152.1
```

### Stödda format
- `energy_wh` (krävs) - Kumulativ energi i Watt-timmar
- `power_w` (valfri) - Momentan effekt i Watt
- `timestamp` format som stöds:
  - `2024-01-01 00:00:00`
  - `2024-01-01T00:00:00`
  - `2024-01-01T00:00:00Z`

## Hur det fungerar

### 1. CSV-nedladdning och parsing
- `ShellyCSVImporter` laddar ner CSV från URL:er
- Parsar och validerar data
- Stöder flera tidsstämpelformat

### 2. Offset-lagring
Efter import lagras total energi som offset:

```json
{
  "energy_offsets": {
    "l1": {
      "value": 10000.0,
      "imported_at": "2024-01-15T10:30:00",
      "source": "http://shelly.local/emeter/0/em_data.csv"
    }
  }
}
```

### 3. Energisensor-integration (TODO)
Energisensorer kommer att exponera både nuvarande och totala värden:

```yaml
sensor.gridenforcer_energy_l1:
  state: 12345.67  # Total (nuvarande + offset)
  attributes:
    current_reading: 2345.67  # Live från Shelly
    historical_offset: 10000.00  # Från CSV-import
    last_import_date: "2024-01-15T10:30:00"
    import_source: "http://shelly.local/emeter/0/em_data.csv"
```

### 4. Statistics-integration
Importen skriver till Home Assistants långtidsstatistik för:
- Energy Dashboard-integration
- Historiska grafer
- Långsiktig trendanalys

## Implementation Status

### ✅ Klar (Fas 1)
- [x] CSV-nedladdare med URL-stöd
- [x] CSV-parser med Shelly-formatstöd
- [x] Service-registrering och schema
- [x] Offset-lagring i config entry
- [x] Statistics-import
- [x] Felhantering och validering
- [x] Service-översättningar

### 🚧 Återstår (Fas 2)
- [ ] Förbättrade energisensorer med offset-stöd
- [ ] Kostnadssensor-integration
- [ ] Historisk kostnadsberäkning
- [ ] Config flow UI för import

## Filer skapade

1. **csv_importer.py** - CSV-nedladdning och parsing
2. **services.py** - Service handler för import
3. **services.yaml** - Service-definition
4. **const.py** - Konstanter (uppdaterad)
5. **strings.json** - Översättningar (uppdaterad)
6. **__init__.py** - Service-registrering (uppdaterad)

## Nästa steg

För att slutföra implementationen:

1. **Skapa förbättrade energisensorer** med offset-stöd
2. **Uppdatera kostnadssensorer** att använda historisk + nuvarande data
3. **Implementera historisk kostnadsberäkning** med spotpriser
4. **Lägg till omfattande tester** för alla komponenter

