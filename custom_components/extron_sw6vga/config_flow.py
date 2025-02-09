import logging
from typing import Any, Optional
import serial  # to test connection
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN, CONF_DEVICE

_LOGGER = logging.getLogger(__name__)


class ExtronSW6ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for Extron SW6VGA integration."""

    VERSION = 1

    async def async_step_user(
        self, user_input: Optional[dict[str, Any]] = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            device_url = user_input[CONF_DEVICE]
            # Basic validation of input
            if not device_url:
                errors["base"] = "no_device"
            else:
                # Check if already configured
                await self.async_set_unique_id(device_url)
                self._abort_if_unique_id_configured()

                # Test connection by trying to open the port (without reading).
                try:
                    # Use serial_for_url in executor to attempt open, then close immediately.
                    def try_open():
                        ser = serial.serial_for_url(
                            device_url, baudrate=9600, timeout=1
                        )
                        ser.close()

                    await self.hass.async_add_executor_job(try_open)
                except Exception as e:
                    _LOGGER.error("Connection test failed for %s: %s", device_url, e)
                    errors["base"] = "cannot_connect"

                if not errors:
                    # Create the entry
                    _LOGGER.debug(
                        "Device %s passed connection test, creating entry", device_url
                    )
                    return self.async_create_entry(
                        title=f"Extron SW6 @ {device_url}",
                        data={CONF_DEVICE: device_url},
                    )
        # Show the form (first time or on errors)
        data_schema = vol.Schema({vol.Required(CONF_DEVICE): str})
        return self.async_show_form(
            step_id="user", data_schema=data_schema, errors=errors
        )
