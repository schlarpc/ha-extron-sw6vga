import logging
from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers import dispatcher

from .const import DOMAIN, SIGNAL_SW6_UPDATE

_LOGGER = logging.getLogger(__name__)

INPUT_OPTIONS = [f"Input {i}" for i in range(1, 7)]  # Options 1 through 6


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
):
    """Set up the select entity for Extron SW6 inputs."""
    sw = hass.data[DOMAIN][entry.entry_id]
    entity = ExtronInputSelect(sw)
    async_add_entities([entity])
    _LOGGER.debug("ExtronInputSelect entity added for %s", sw.device_url)


class ExtronInputSelect(SelectEntity):
    """Select entity to choose the active input on the Extron switcher."""

    def __init__(self, sw):
        self._sw = sw
        self._attr_name = "Extron Active Input"
        self._attr_options = INPUT_OPTIONS
        # Unique ID for entity can be based on device and entity type
        self._attr_unique_id = f"{sw.device_url}_input_select"
        # Associate with device in HA device registry
        self._attr_device_info: DeviceInfo = sw.device_info

    @property
    def current_option(self) -> str:
        """Return the current selected option."""
        if self._sw.current_input is None:
            return None
        return f"Input {self._sw.current_input}"

    async def async_select_option(self, option: str) -> None:
        """Handle user selecting a new input option."""
        # Parse the selected option string back to a number
        try:
            # Option format is "Input X"
            input_num = int(option.split(" ")[1])
        except Exception as e:
            _LOGGER.error("Invalid option format: %s", option)
            return
        _LOGGER.debug("Input select option chosen: %s", input_num)
        # Use executor to send command via serial client
        await self._sw.hass.async_add_executor_job(self._sw.set_input, input_num)
        # Note: state will be updated when the response is received from the device

    @property
    def available(self) -> bool:
        """Entity availability based on connection."""
        return self._sw.available

    async def async_added_to_hass(self):
        """When entity is added, register for updates."""
        # Listen to dispatcher signal to refresh state
        self.async_on_remove(
            dispatcher.dispatcher_connect(
                self.hass, SIGNAL_SW6_UPDATE, self._update_callback
            )
        )

    @callback
    def _update_callback(self):
        """Call when the Extron state changes."""
        _LOGGER.debug("Input select update callback triggered")
        self.async_write_ha_state()
