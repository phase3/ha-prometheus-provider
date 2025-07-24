"""Sensor platform for Prometheus Provider integration."""
import logging
from typing import Any, Dict, Optional, Callable

from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    CONF_PROMETHEUS_URL,
    CONF_SCRAPE_INTERVAL,
    CONF_TARGETS,
    CONF_TARGET_NAME,
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    CONF_DEVICE_MANUFACTURER,
    CONF_DEVICE_MODEL,
    DEFAULT_SCRAPE_INTERVAL,
    DEFAULT_MANUFACTURER,
    DATA_COORDINATORS, # Added import
)
from .coordinator import PrometheusDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,  # Full HA config
    async_add_entities: Callable,
    discovery_info: Optional[DiscoveryInfoType] = None,
) -> None:
    """Set up the Prometheus Provider sensor platform from YAML."""
    _LOGGER.debug("Setting up Prometheus Provider sensor platform for YAML.")

    if not (discovery_info and discovery_info.get("yaml")):
        _LOGGER.debug("Not a YAML setup call (no discovery_info or 'yaml' key missing), skipping sensor platform setup.")
        return

    coordinators = hass.data.get(DOMAIN, {}).get(DATA_COORDINATORS)
    if not coordinators:
        _LOGGER.warning(
            "No Prometheus coordinators found in hass.data[DOMAIN][DATA_COORDINATORS]. "
            "Ensure the integration is correctly configured in YAML and __init__.py ran successfully."
        )
        return

    sensors_to_add = []
    for coordinator_key, coordinator in coordinators.items():
        _LOGGER.debug(f"Processing coordinator: {coordinator.name} (key: {coordinator_key})")

        # Perform initial refresh to populate coordinator.data
        # This is crucial for discovering sensors at startup for YAML config,
        # as __init__.py defers this to the platform.
        try:
            await coordinator.async_config_entry_first_refresh()
        except Exception as e:  # Catch potential UpdateFailed or other errors during refresh
            _LOGGER.error(f"Initial data fetch failed for coordinator {coordinator.name}: {e}")
            continue  # Skip this coordinator if refresh fails

        if not coordinator.data:
            _LOGGER.warning(
                "Initial data fetch yielded no data for coordinator %s. "
                "No sensors will be created for this target.",
                coordinator.name,
            )
            continue
        
        _LOGGER.debug("Coordinator data for %s: %s", coordinator.name, coordinator.data)
        
        # Get target_config from the coordinator instance, where it was stored by __init__.py
        target_config = coordinator.target_config

        # Create sensors based on the initial data fetched by the coordinator
        for metric_key, metric_data in coordinator.data.items():
            sensors_to_add.append(
                PrometheusSensor(
                    coordinator=coordinator,
                    metric_key=metric_key,
                    target_config=target_config, # Use the target_config from the coordinator
                )
            )

    if sensors_to_add:
        _LOGGER.info("Adding %s Prometheus sensors from YAML configuration.", len(sensors_to_add))
        if callable(async_add_entities):
            async_add_entities(sensors_to_add, True) # True for update_before_add
        else:
            _LOGGER.error("async_add_entities is not callable - entity addition failed")
    else:
        _LOGGER.info("No Prometheus sensors to add from YAML configuration. Check coordinator data and target setups.")


class PrometheusSensor(CoordinatorEntity[PrometheusDataUpdateCoordinator], SensorEntity):
    """Representation of a Prometheus sensor."""

    def __init__(
        self,
        coordinator: PrometheusDataUpdateCoordinator,
        metric_key: str, # Unique key for the metric (name + labels)
        target_config: Dict[str, Any],
    ):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._metric_key = metric_key
        self._target_config = target_config
        
        # Initial data for attributes, will be updated by _handle_coordinator_update
        metric_data = coordinator.data.get(self._metric_key, {})
        self._metric_name = metric_data.get("name", self._metric_key) # Fallback to key
        self._metric_labels = metric_data.get("labels", {})

        # Construct unique ID and name
        device_id = self._target_config.get(CONF_DEVICE_ID, self._metric_name) # Fallback
        
        # Sanitize metric name and labels for unique_id and entity_id
        sanitized_metric_name = self._metric_name.replace(".", "_").replace("-", "_")
        
        # Create a string from sorted labels (key_value)
        # This ensures consistent ID regardless of label order from Prometheus
        label_parts = [
            f"{key.replace('.', '_').replace('-', '_')}_{value.replace('.', '_').replace('-', '_')}"
            for key, value in sorted(self._metric_labels.items())
        ]
        label_suffix = "_".join(label_parts) if label_parts else ""

        self._attr_unique_id = f"{DOMAIN}_{device_id}_{sanitized_metric_name}"
        if label_suffix:
            self._attr_unique_id += f"_{label_suffix}"
        
        # Friendly name construction
        name_parts = [self._target_config.get(CONF_DEVICE_NAME, device_id)]
        name_parts.append(self._metric_name)
        if self._metric_labels:
            label_desc = ", ".join(f"{k}={v}" for k, v in self._metric_labels.items())
            name_parts.append(f"({label_desc})")
        self._attr_name = " ".join(name_parts)

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            name=self._target_config.get(CONF_DEVICE_NAME, device_id),
            manufacturer=self._target_config.get(CONF_DEVICE_MANUFACTURER, DEFAULT_MANUFACTURER),
            model=self._target_config.get(CONF_DEVICE_MODEL),
            via_device=(DOMAIN, DOMAIN), # Links to the integration itself
        )
        
        # Set initial state and attributes
        self._update_sensor_attributes(metric_data)


    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        metric_data = self.coordinator.data.get(self._metric_key)
        if metric_data:
            self._update_sensor_attributes(metric_data)
            self.async_write_ha_state()
        else:
            # Metric might have disappeared
            _LOGGER.debug("Metric %s no longer available for sensor %s", self._metric_key, self.entity_id)
            # Optionally set to unavailable, or handle as per requirements
            # For now, it will retain its last state if not updated.
            # To make it unavailable:
            # self._attr_available = False
            # self.async_write_ha_state()
            pass


    def _update_sensor_attributes(self, metric_data: Dict[str, Any]):
        """Update sensor state and attributes from metric data."""
        self._attr_native_value = metric_data.get("value")
        self._metric_labels = metric_data.get("labels", {}) # Update labels too
        
        # Attempt to infer unit, device_class, state_class
        # This is a simplified example; a more robust parser would be needed.
        raw_metric_name = metric_data.get("name", "")

        if "_bytes" in raw_metric_name:
            self._attr_native_unit_of_measurement = "bytes"
            self._attr_device_class = SensorDeviceClass.DATA_SIZE
        elif "_seconds" in raw_metric_name:
            self._attr_native_unit_of_measurement = "s"
            self._attr_device_class = SensorDeviceClass.DURATION
        elif "_celsius" in raw_metric_name or "temperature_celsius" in raw_metric_name:
            self._attr_native_unit_of_measurement = "°C"
            self._attr_device_class = SensorDeviceClass.TEMPERATURE
        elif "_fahrenheit" in raw_metric_name or "temperature_fahrenheit" in raw_metric_name:
            self._attr_native_unit_of_measurement = "°F"
            self._attr_device_class = SensorDeviceClass.TEMPERATURE
        elif "_percent" in raw_metric_name or "_ratio" in raw_metric_name:
            self._attr_native_unit_of_measurement = "%"
            self._attr_device_class = SensorDeviceClass.POWER_FACTOR # Or other percentage based class
        elif "voltage" in raw_metric_name:
            self._attr_native_unit_of_measurement = "V"
            self._attr_device_class = SensorDeviceClass.VOLTAGE
        elif "current" in raw_metric_name or "amperes" in raw_metric_name:
            self._attr_native_unit_of_measurement = "A"
            self._attr_device_class = SensorDeviceClass.CURRENT
        elif "energy_kwh" in raw_metric_name or "_kwh" in raw_metric_name:
            self._attr_native_unit_of_measurement = "kWh"
            self._attr_device_class = SensorDeviceClass.ENERGY
        elif "power_watts" in raw_metric_name or "_watts" in raw_metric_name:
            self._attr_native_unit_of_measurement = "W"
            self._attr_device_class = SensorDeviceClass.POWER
        else:
            self._attr_native_unit_of_measurement = None
            self._attr_device_class = None
            # Try to guess icon based on common terms
            if "cpu" in raw_metric_name: self._attr_icon = "mdi:cpu-64-bit"
            elif "memory" in raw_metric_name: self._attr_icon = "mdi:memory"
            elif "disk" in raw_metric_name: self._attr_icon = "mdi:harddisk"
            elif "network" in raw_metric_name: self._attr_icon = "mdi:network-outline"
            elif "process" in raw_metric_name: self._attr_icon = "mdi:cogs"
            else: self._attr_icon = "mdi:chart-line"


        # State class (MEASUREMENT, TOTAL, TOTAL_INCREASING)
        if "_total" in raw_metric_name or raw_metric_name.endswith("_count"): # Common for counters
            self._attr_state_class = SensorStateClass.TOTAL_INCREASING
        else: # Gauges
            self._attr_state_class = SensorStateClass.MEASUREMENT
        
        # Store all labels as extra attributes
        self._attr_extra_state_attributes = self._metric_labels.copy()
        self._attr_extra_state_attributes["prometheus_metric_name"] = raw_metric_name
        self._attr_extra_state_attributes["prometheus_metric_key"] = self._metric_key
        self._attr_extra_state_attributes["last_synced_timestamp"] = metric_data.get("timestamp")

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        # Sensor is available if the coordinator has data for this metric_key
        return self.coordinator.last_update_success and self._metric_key in self.coordinator.data