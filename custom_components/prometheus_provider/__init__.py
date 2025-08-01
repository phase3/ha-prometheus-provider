"""The Prometheus Provider integration."""
import asyncio
import logging
from typing import Dict

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import discovery
from homeassistant.const import (
    CONF_NAME,
)

from .const import (
    DOMAIN,
    CONF_PROMETHEUS_URL,
    CONF_SCRAPE_INTERVAL,
    CONF_TARGETS,
    CONF_TARGET_NAME,
    CONF_JOB_NAME,
    CONF_INSTANCE_VALUE,
    CONF_METRICS_PREFIX,
    CONF_INCLUDED_METRICS,
    CONF_EXCLUDED_METRICS,
    CONF_METRICS_FILTER,
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    CONF_DEVICE_MANUFACTURER,
    CONF_DEVICE_MODEL,
    DEFAULT_SCRAPE_INTERVAL,
    DEFAULT_MANUFACTURER,
    DATA_COORDINATORS,
)
from .coordinator import PrometheusDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor"]

TARGET_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_TARGET_NAME): cv.string,
        vol.Required(CONF_JOB_NAME): cv.string,
        vol.Required(CONF_INSTANCE_VALUE): cv.string,
        vol.Required(CONF_DEVICE_ID): cv.slug,
        vol.Required(CONF_DEVICE_NAME): cv.string,
        vol.Optional(CONF_DEVICE_MANUFACTURER, default=DEFAULT_MANUFACTURER): cv.string,
        vol.Optional(CONF_DEVICE_MODEL): cv.string,
        vol.Optional(CONF_METRICS_PREFIX): cv.string,
        vol.Optional(CONF_INCLUDED_METRICS): vol.All(cv.ensure_list, [cv.string]),
        vol.Optional(CONF_EXCLUDED_METRICS): vol.All(cv.ensure_list, [cv.string]),
        vol.Optional(CONF_METRICS_FILTER): vol.Schema({cv.string: cv.string}),
        vol.Optional(
            CONF_SCRAPE_INTERVAL, default=DEFAULT_SCRAPE_INTERVAL
        ): cv.positive_int,
    }
)

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Required(CONF_PROMETHEUS_URL): cv.url,
                vol.Optional(
                    CONF_SCRAPE_INTERVAL, default=DEFAULT_SCRAPE_INTERVAL
                ): cv.positive_int, # Global scrape interval
                vol.Required(CONF_TARGETS): vol.All(cv.ensure_list, [TARGET_SCHEMA]),
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Prometheus Provider integration from YAML configuration."""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][DATA_COORDINATORS] = {}

    if DOMAIN not in config:
        return True

    integration_config = config[DOMAIN]
    prometheus_url = integration_config[CONF_PROMETHEUS_URL]
    global_scrape_interval = integration_config[CONF_SCRAPE_INTERVAL]
    targets = integration_config[CONF_TARGETS]

    session = async_get_clientsession(hass)

    for target_config in targets:
        target_name = target_config[CONF_TARGET_NAME]
        # Use target-specific scrape interval if defined, else global, else default
        scrape_interval = target_config.get(CONF_SCRAPE_INTERVAL, global_scrape_interval)

        coordinator = PrometheusDataUpdateCoordinator(
            hass=hass,
            name=f"{DOMAIN} {target_name}", # Unique name for the coordinator
            prometheus_url=prometheus_url,
            scrape_interval=scrape_interval,
            target_config=target_config,
        )
        # No initial refresh here for YAML, platform will trigger or first update will run
        hass.data[DOMAIN][DATA_COORDINATORS][target_name] = coordinator

    # Forward setup to sensor platform.
    # The sensor platform will retrieve coordinators from hass.data.
    if targets: # Only load platform if there are targets
        # Mark that this is YAML setup in hass.data for the sensor platform to detect
        hass.data[DOMAIN]["yaml_setup"] = True
        
        # Load platforms using the most compatible method
        for platform in PLATFORMS:
            hass.async_create_task(
                _async_load_platform(hass, platform, config)
            )

    return True


async def _async_load_platform(hass: HomeAssistant, platform: str, config: ConfigType) -> None:
    """Load a platform with error handling for different HA versions."""
    try:
        # Try modern discovery method first
        await discovery.async_load_platform(
            hass, platform, DOMAIN, {"yaml": True}, config
        )
        _LOGGER.debug("Successfully loaded %s platform using discovery", platform)
    except (AttributeError, ImportError) as err:
        _LOGGER.debug("Discovery method failed (%s), trying direct platform loading", err)
        try:
            # Fallback to direct platform loading
            if platform == "sensor":
                from . import sensor
                
                # Create a proper async_add_entities function
                from homeassistant.helpers.entity_platform import async_get_current_platform
                
                async def async_add_entities_wrapper(entities, update_before_add=True):
                    """Add entities using the current platform."""
                    current_platform = async_get_current_platform()
                    if current_platform:
                        await current_platform.async_add_entities(entities, update_before_add)
                    else:
                        _LOGGER.error("No current platform available for adding entities")
                
                await sensor.async_setup_platform(
                    hass, config, async_add_entities_wrapper, {"yaml": True}
                )
                _LOGGER.debug("Successfully loaded %s platform using direct method", platform)
        except Exception as fallback_err:
            _LOGGER.error("Failed to load %s platform: %s", platform, fallback_err)
    except Exception as err:
        _LOGGER.error("Unexpected error loading %s platform: %s", platform, err)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Prometheus Provider from a config entry."""
    # This function is called when a config entry is created (e.g., via UI).
    # The current manifest.json has "config_flow": false, so this won't be used yet.
    # However, it's good practice to implement it for future UI configuration.

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN].setdefault(DATA_COORDINATORS, {})

    # Config entry data typically comes from user input during config flow
    # For this example, let's assume the entry.data holds a single target's config
    # and prometheus_url. If multiple targets per entry, structure would differ.
    # Based on prometheus_integration_architecture.md, one coordinator per target.
    # If a config entry represents ONE target:
    prometheus_url = entry.data[CONF_PROMETHEUS_URL]
    target_config = entry.data # Assuming entry.data is the target_config itself
    target_name = target_config[CONF_TARGET_NAME]
    scrape_interval = entry.options.get(CONF_SCRAPE_INTERVAL, target_config.get(CONF_SCRAPE_INTERVAL, DEFAULT_SCRAPE_INTERVAL))


    coordinator = PrometheusDataUpdateCoordinator(
        hass=hass,
        name=f"{DOMAIN} {entry.title}", # entry.title is usually user-friendly name
        prometheus_url=prometheus_url,
        scrape_interval=scrape_interval,
        target_config=target_config, # Pass the specific target config
    )

    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][DATA_COORDINATORS][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN][DATA_COORDINATORS].pop(entry.entry_id)
        if not hass.data[DOMAIN][DATA_COORDINATORS]: # If no more coordinators for this domain
            hass.data[DOMAIN].pop(DATA_COORDINATORS) # Clean up the coordinators dict
            # Consider if hass.data[DOMAIN] itself should be popped if empty and no YAML config
    return unload_ok

async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)