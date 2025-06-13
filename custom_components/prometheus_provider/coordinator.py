"""DataUpdateCoordinator for the Prometheus Provider integration."""
import asyncio
from datetime import timedelta
import logging
from typing import Any, Dict, List, Optional

import async_timeout
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    DOMAIN,
    CONF_PROMETHEUS_URL,
    CONF_JOB_NAME,
    CONF_INSTANCE_LABEL,
    CONF_INSTANCE_VALUE,
    CONF_METRICS_FILTER,
    CONF_METRICS_PREFIX,
    CONF_INCLUDED_METRICS,
    CONF_EXCLUDED_METRICS,
)

_LOGGER = logging.getLogger(__name__)

# Placeholder for prometheus_client_wrapper functions
# Will be replaced with actual import or direct implementation
async def async_get_prometheus_metrics(
    session,
    prometheus_url: str,
    job_name: str,
    instance_label: str,
    instance_value: str,
    metrics_filter: Optional[Dict[str, str]] = None
) -> List[Dict[str, Any]]:
    """
    Fetch metrics from Prometheus API.
    This is a simplified placeholder. A more robust implementation is needed.
    Example query: {job="<job_name>", <instance_label>="<instance_value>", ...<metrics_filter>}
    """
    # Construct PromQL query
    label_selectors = [
        f'{CONF_JOB_NAME}="{job_name}"',
        f'{instance_label}="{instance_value}"'
    ]
    if metrics_filter:
        for key, value in metrics_filter.items():
            label_selectors.append(f'{key}="{value}"')
    
    query = "{" + ",".join(label_selectors) + "}"
    
    # Use /api/v1/query for instant vector
    # For simplicity, we'll query for all metrics matching the labels.
    # A more advanced approach might use /api/v1/series then /api/v1/query_range or /api/v1/query
    # or directly parse /metrics endpoint if that's preferred for some targets.
    # This example targets /api/v1/query with a simple selector.
    # query_url = f"{prometheus_url.rstrip('/')}/api/v1/query?query={query}" # This would get current values
    
    # A more common way to get all metrics for a target is to use /api/v1/targets and then scrape,
    # or use /api/v1/series with matchers, then /api/v1/query for values.
    # For now, let's assume a query that fetches all relevant series and their current values.
    # This is a complex part and prometheus_client library might be better.
    # Let's use a query that fetches all metrics for the job and instance.
    # This is a placeholder for actual API interaction.
    query_url = f"{prometheus_url.rstrip('/')}/api/v1/query?query={query}"
    _LOGGER.debug("Querying Prometheus: %s", query_url)

    try:
        async with async_timeout.timeout(10):
            response = await session.get(query_url)
            response.raise_for_status()
            data = await response.json()
            _LOGGER.debug("Prometheus response: %s", data)

            if data.get("status") == "success":
                result = data.get("data", {}).get("result", [])
                # Format: [{"metric": {"__name__": "metric_name", "label1": "val1"}, "value": [timestamp, "value_str"]}]
                return result 
            else:
                _LOGGER.error("Prometheus API error: %s", data.get("error", "Unknown error"))
                return []
    except asyncio.TimeoutError:
        _LOGGER.error("Timeout connecting to Prometheus API at %s", prometheus_url)
        raise UpdateFailed(f"Timeout connecting to Prometheus API at {prometheus_url}")
    except Exception as e:
        _LOGGER.error("Error connecting to Prometheus API at %s: %s", prometheus_url, e)
        raise UpdateFailed(f"Error connecting to Prometheus API: {e}")


class PrometheusDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Prometheus data."""

    def __init__(
        self,
        hass: HomeAssistant,
        name: str,
        prometheus_url: str,
        scrape_interval: int,
        target_config: Dict[str, Any],
    ):
        """Initialize."""
        self.prometheus_url = prometheus_url
        self.target_config = target_config
        self.session = async_get_clientsession(hass)
        self.name = name # Usually derived from target_name or device_name

        super().__init__(
            hass,
            _LOGGER,
            name=name,
            update_interval=timedelta(seconds=scrape_interval),
        )

    async def _async_update_data(self) -> Dict[str, Any]:
        """Fetch data from Prometheus."""
        _LOGGER.debug("Fetching data for target %s", self.name)
        job_name = self.target_config[CONF_JOB_NAME]
        instance_label = self.target_config[CONF_INSTANCE_LABEL]
        instance_value = self.target_config[CONF_INSTANCE_VALUE]
        metrics_filter = self.target_config.get(CONF_METRICS_FILTER)
        
        # These filters will be applied *after* fetching all metrics for the job/instance
        # A more efficient way would be to incorporate them into the PromQL query if possible
        # or use /api/v1/series with 'match[]' parameter.
        metrics_prefix = self.target_config.get(CONF_METRICS_PREFIX)
        included_metrics = self.target_config.get(CONF_INCLUDED_METRICS)
        excluded_metrics = self.target_config.get(CONF_EXCLUDED_METRICS, [])


        try:
            # raw_metrics is a list of dicts, e.g.
            # [{"metric": {"__name__": "metric_name", "label1": "val1"}, "value": [timestamp, "value_str"]}]
            raw_metrics = await async_get_prometheus_metrics(
                self.session,
                self.prometheus_url,
                job_name,
                instance_label,
                instance_value,
                metrics_filter,
            )

            processed_metrics = {}
            for item in raw_metrics:
                metric_labels = item.get("metric", {})
                metric_name = metric_labels.get("__name__")
                
                if not metric_name:
                    continue

                # Apply filters
                if metrics_prefix and not metric_name.startswith(metrics_prefix):
                    continue
                if included_metrics and metric_name not in included_metrics:
                    continue
                if metric_name in excluded_metrics:
                    continue

                # Create a unique key for each metric based on its name and labels
                # Sort labels to ensure consistent key generation
                labels_key_part = "_".join(
                    f"{k}_{v}" for k, v in sorted(metric_labels.items()) if k != "__name__"
                )
                metric_key = f"{metric_name}_{labels_key_part}" if labels_key_part else metric_name
                
                # value is [timestamp, value_str]
                value_pair = item.get("value")
                if value_pair and len(value_pair) == 2:
                    processed_metrics[metric_key] = {
                        "name": metric_name,
                        "labels": {k: v for k, v in metric_labels.items() if k != "__name__"},
                        "value": value_pair[1], # The actual value string
                        "timestamp": value_pair[0], # Timestamp of the value
                    }
            _LOGGER.debug("Processed metrics for %s: %s", self.name, processed_metrics)
            return processed_metrics
        except UpdateFailed as err:
            _LOGGER.warning("Update failed for %s: %s", self.name, err)
            raise
        except Exception as err:
            _LOGGER.error("Unexpected error updating data for %s: %s", self.name, err)
            raise UpdateFailed(f"Unexpected error: {err}")