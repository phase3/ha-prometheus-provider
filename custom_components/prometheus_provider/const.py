"""Constants for the Prometheus Provider integration."""

DOMAIN = "prometheus_provider"

# Configuration Keys
CONF_PROMETHEUS_URL = "prometheus_url"
CONF_SCRAPE_INTERVAL = "scrape_interval"
CONF_TARGETS = "targets"
CONF_TARGET_NAME = "target_name"
CONF_JOB_NAME = "job_name"
CONF_INSTANCE_VALUE = "instance_value"
CONF_DEVICE_ID = "device_id"
CONF_DEVICE_NAME = "device_name"
CONF_DEVICE_MANUFACTURER = "device_manufacturer"
CONF_DEVICE_MODEL = "device_model"
CONF_METRICS_PREFIX = "metrics_prefix"
CONF_INCLUDED_METRICS = "included_metrics"
CONF_EXCLUDED_METRICS = "excluded_metrics"
CONF_METRICS_FILTER = "metrics_filter"


# Data keys
DATA_COORDINATORS = "coordinators"

# Defaults
DEFAULT_SCRAPE_INTERVAL = 60  # seconds
DEFAULT_MANUFACTURER = "Prometheus"