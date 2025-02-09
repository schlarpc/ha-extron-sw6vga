"""Constants for the Extron SW6VGA integration."""

DOMAIN = "extron_sw6"

# Config entry fields (if we had more, e.g., host, port separate, but here we'll use one device URL field)
CONF_DEVICE = "device_url"

# Default serial settings for SW6 (for reference, if needed)
DEFAULT_BAUDRATE = 9600
DEFAULT_TIMEOUT = 1.0  # seconds

# Dispatcher signal for state updates
SIGNAL_SW6_UPDATE = "extron_sw6_update"
