import logging
from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers import dispatcher

from .const import DOMAIN, SIGNAL_SW6_UPDATE

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
):
    """Set up the switch entity for Extron auto-switch mode."""
    sw = hass.data[DOMAIN][entry.entry_id]
    entity = ExtronAutoSwitchToggle(sw)
    async_add_entities([entity])
    _LOGGER.debug("ExtronAutoSwitchToggle entity added for %s", sw.device_url)


class ExtronAutoSwitchToggle(SwitchEntity):
    """Switch entity to control the Auto Switch mode on the Extron device."""

    def __init__(self, sw):
        self._sw = sw
        self._attr_name = "Extron Auto Switch Mode"
        self._attr_unique_id = f"{sw.device_url}_auto_mode"
        self._attr_device_info: DeviceInfo = sw.device_info

    @property
    def is_on(self) -> bool:
        """Return True if auto-switch mode is enabled."""
        return self._sw.auto_mode

    async def async_turn_on(self, **kwargs):
        """Enable auto-switch mode."""
        _LOGGER.debug("Turning ON auto-switch mode")
        await self._sw.hass.async_add_executor_job(self._sw.set_auto_mode, True)

    async def async_turn_off(self, **kwargs):
        """Disable auto-switch mode (switch to manual)."""
        _LOGGER.debug("Turning OFF auto-switch mode")
        await self._sw.hass.async_add_executor_job(self._sw.set_auto_mode, False)

    @property
    def available(self) -> bool:
        """Availability based on connection."""
        return self._sw.available

    async def async_added_to_hass(self):
        """Register for state updates."""
        self.async_on_remove(
            dispatcher.dispatcher_connect(self.hass, SIGNAL_SW6_UPDATE, self._refresh)
        )

    @callback
    def _refresh(self):
        """Update state when notified."""
        _LOGGER.debug("Auto mode switch update callback triggered")
        self.async_write_ha_state()
