# Prometheus Provider for Home Assistant

A custom Home Assistant integration that provides sensor entities from Prometheus metrics.

## Features

- Fetch metrics from Prometheus API
- Create Home Assistant sensors from Prometheus metrics
- Support for multiple targets with different configurations
- Automatic device creation and organization
- Configurable metric filtering and prefixes
- Support for metric labels as sensor attributes

## Installation

### HACS (Recommended)

1. Open HACS in your Home Assistant instance
2. Go to "Integrations"
3. Click the three dots in the top right corner
4. Select "Custom repositories"
5. Add this repository URL and select "Integration" as the category
6. Click "Install"
7. Restart Home Assistant

### Manual Installation

1. Copy the `custom_components/prometheus_provider` folder to your Home Assistant `custom_components` directory
2. Restart Home Assistant

## Configuration

Add the following to your `configuration.yaml`:

```yaml
prometheus_provider:
  prometheus_url: "http://your-prometheus-server:9090"
  scrape_interval: 60  # Optional, default is 60 seconds
  targets:
    - target_name: "my_server"
      job_name: "node_exporter"
      instance_value: "server.local:9100"
      device_id: "my_server"
      device_name: "My Server"
      device_manufacturer: "Custom"  # Optional
      device_model: "Server"  # Optional
      metrics_prefix: "node_"  # Optional
      included_metrics:  # Optional
        - "node_cpu_seconds_total"
        - "node_memory_MemTotal_bytes"
      excluded_metrics:  # Optional
        - "node_network_receive_drop_total"
      metrics_filter:  # Optional
        cpu: "0"
      scrape_interval: 30  # Optional, overrides global setting
```

## Configuration Options

### Global Options

- `prometheus_url`: URL of your Prometheus server (required)
- `scrape_interval`: How often to fetch metrics in seconds (optional, default: 60)
- `targets`: List of target configurations (required)

### Target Options

- `target_name`: Unique name for this target (required)
- `job_name`: Prometheus job name to query (required)
- `instance_value`: Instance value to filter by (required)
- `device_id`: Unique device identifier (required)
- `device_name`: Human-readable device name (required)
- `device_manufacturer`: Device manufacturer (optional, default: "Prometheus")
- `device_model`: Device model (optional)
- `metrics_prefix`: Only include metrics starting with this prefix (optional)
- `included_metrics`: List of specific metrics to include (optional)
- `excluded_metrics`: List of metrics to exclude (optional)
- `metrics_filter`: Additional label filters as key-value pairs (optional)
- `scrape_interval`: Target-specific scrape interval (optional)

## Support

For issues and feature requests, please use the [GitHub issue tracker](https://github.com/phase3/ha-prometheus-provider/issues).

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.