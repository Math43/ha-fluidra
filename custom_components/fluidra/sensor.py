from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import FluidraCoordinator

SENSOR_DESCRIPTIONS: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key="value_ph",
        name="pH",
        icon="mdi:ph",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="value_water_temperature",
        name="Water Temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
    ),
    SensorEntityDescription(
        key="value_power",
        name="Chlorinator Power",
        icon="mdi:lightning-bolt",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
    ),
    SensorEntityDescription(
        key="value_salinity",
        name="Salinity",
        icon="mdi:water-percent",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="g/L",
    ),
    SensorEntityDescription(
        key="set_ph",
        name="pH Setpoint",
        icon="mdi:ph",
    ),
    SensorEntityDescription(
        key="set_power",
        name="Chlorinator Power Setpoint",
        icon="mdi:lightning-bolt-outline",
        native_unit_of_measurement=PERCENTAGE,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: FluidraCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        FluidraSensor(coordinator, description)
        for description in SENSOR_DESCRIPTIONS
    )


class FluidraSensor(CoordinatorEntity[FluidraCoordinator], SensorEntity):
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: FluidraCoordinator,
        description: SensorEntityDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.device_id}_{description.key}"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.device_id)},
            name="Fluidra Pool",
            manufacturer="Fluidra",
        )

    @property
    def native_value(self):
        return self.coordinator.data.get(self.entity_description.key)
