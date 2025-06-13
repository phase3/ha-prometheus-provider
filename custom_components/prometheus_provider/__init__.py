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
    CONF_INSTANCE_LABEL,
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
        vol.Required(CONF_INSTANCE_LABEL): cv.string,
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
        hass.async_create_task(
            hass.config_entries.async_setup_platforms(None, PLATFORMS) # Pass None as entry for YAML setup
        )
        # For YAML, we might need a way for sensor platform to know it's YAML setup.
        # Storing a flag or using a special key in hass.data might be one way.
        # Or sensor platform checks if entry is None.
        # The current sensor.py template expects an entry.
        # Let's adjust sensor.py later to handle this.
        # For now, this is a placeholder for how platforms are typically loaded.
        # A more common pattern for YAML is hass.helpers.discovery.load_platform.
        # However, with coordinators, it's better if platforms can access them directly.

        # Let's use discovery.async_load_platform as it's more suited for YAML
        # and sensor.py can then iterate hass.data[DOMAIN][DATA_COORDINATORS]
        for platform in PLATFORMS:
            hass.async_create_task(
                hass.helpers.discovery.async_load_platform(
                    platform, DOMAIN, {"yaml": True}, config # Pass a marker for YAML
                )
            )

    return True


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