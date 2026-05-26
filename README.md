# Fluidra — Home Assistant Custom Integration

Custom integration for Fluidra EMEA pool equipment (chlorinators). Based on reverse engineering of the Fluidra mobile app API.

## Supported devices

Tested with: iAquaLink salt chlorinator connected via Fluidra EMEA app.

## Sensors

| Entity | Description | Unit |
|--------|-------------|------|
| `sensor.fluidra_pool_ph` | Measured pH | — |
| `sensor.fluidra_pool_water_temperature` | Water temperature | °C |
| `sensor.fluidra_pool_chlorinator_power` | Chlorinator output | % |
| `sensor.fluidra_pool_salinity` | Salinity | g/L |
| `sensor.fluidra_pool_ph_setpoint` | pH target setpoint | — |
| `sensor.fluidra_pool_chlorinator_power_setpoint` | Power target setpoint | % |

## Installation

### Via HACS (recommended)

1. HACS → Custom repositories → Add `https://github.com/Math43/ha-fluidra` (type: Integration)
2. Search "Fluidra" → Install
3. Restart Home Assistant

### Manual

Copy `custom_components/fluidra/` into your `config/custom_components/` folder and restart Home Assistant.

## Configuration

Settings → Devices & Services → Add Integration → **Fluidra**

Enter your Fluidra app credentials (email + password).

## Notes

- Data is polled every 5 minutes
- Requires an active Fluidra EMEA account (`api.fluidra-emea.com`)
- Write support (setting power/pH) is not yet implemented
