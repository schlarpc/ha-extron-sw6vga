import logging
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers import dispatcher
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.exceptions import ConfigEntryNotReady

from .const import DOMAIN, CONF_DEVICE, SIGNAL_SW6_UPDATE
from .extron_serial import ExtronSerialClient

_LOGGER = logging.getLogger(__name__)


# We will store active connections in hass.data[DOMAIN] by entry ID
async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Extron SW6VGA from a config entry."""
    device_url = entry.data[CONF_DEVICE]
    _LOGGER.debug("Setting up Extron SW6VGA entry: device_url=%s", device_url)

    # Create the ExtronSerialClient and state-tracking
    sw = ExtronSwitcher(hass, device_url, entry)
    try:
        await hass.async_add_executor_job(
            sw.connect
        )  # open connection in executor (thread)
    except Exception as err:
        _LOGGER.error("Error connecting to Extron SW6 at %s: %s", device_url, err)
        raise ConfigEntryNotReady(f"Connection failed: {err}")  # will retry

    # Save the instance for later use (e.g., by platforms)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = sw

    # Forward setup to platforms
    await hass.config_entries.async_forward_entry_setups(entry, ["select", "switch"])
    _LOGGER.info("Extron SW6VGA integration set up successfully for %s", device_url)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info("Unloading Extron SW6VGA entry %s", entry.entry_id)
    # Remove entities
    await hass.config_entries.async_unload_platforms(entry, ["select", "switch"])
    # Disconnect the device
    sw: ExtronSwitcher = hass.data[DOMAIN].pop(entry.entry_id, None)
    if sw:
        await hass.async_add_executor_job(sw.disconnect)
    return True


class ExtronSwitcher:
    """
    High-level manager for the Extron SW6 switcher.
    Holds the current state and provides methods to change it.
    """

    def __init__(self, hass: HomeAssistant, device_url: str, config_entry: ConfigEntry):
        self.hass = hass
        self.device_url = device_url
        self.config_entry = config_entry
        # Current state variables
        self.current_input: int = None
        self.audio_input: int = None
        self.auto_mode: bool = False  # False = manual, True = auto
        self.available: bool = False  # track connection status
        # Serial client for communication
        self._client = ExtronSerialClient(device_url, on_message=self._handle_message)

        # Prepare device info for Home Assistant device registry
        self.device_info = DeviceInfo(
            identifiers={(DOMAIN, device_url)},  # using the address as unique id
            name="Extron SW6 VGA Switcher",
            manufacturer="Extron",
            model="SW6 VGA Audio",
            sw_version=None,  # we'll set after querying, if available
        )

    def connect(self):
        """Connect to the device and perform initial state sync."""
        self._client.connect()
        self.available = True
        _LOGGER.debug("Connection established, querying initial status...")
        # Send an information request to get current state (mode, input, etc.)
        # According to Extron SIS, sending "I" (or possibly just a carriage return) returns status.
        # We'll use the documented query command for status.
        self._client.send_command("I")

    def disconnect(self):
        """Disconnect from device."""
        self._client.disconnect()
        self.available = False

    def _handle_message(self, message: str):
        """
        Handle a message received from the device.
        This is called from the serial reader thread.
        """
        # Process the message and update state accordingly
        msg = message.strip()
        if not msg:
            return
        # The device might send multiple types of responses/events:
        if msg.startswith("In") or msg.startswith("IN"):
            # This is a response to an input select or gain query, e.g. "In3 All" or "IN3•AUD=+7"
            # We only care if it's an input selection confirmation (contains "All", "Vid", or "Aud").
            if "All" in msg or "Vid" in msg or "Aud" in msg:
                # Example: "In5 All" -> input 5 selected (both audio & video)
                # "In2 Vid" -> video switched to 2 (audio unchanged)
                # "In4 Aud" -> audio switched to 4 (video unchanged)
                # We'll interpret "All" or presence of "Vid/Aud" accordingly.
                # Simplest approach: parse the number after "In".
                try:
                    num_str = msg[2:].split()[0]  # e.g. "5" from "In5"
                    current = int(num_str)
                except Exception:
                    _LOGGER.warning("Could not parse input from message: %r", msg)
                    current = None
                if current is not None:
                    # If it's "All" or "Vid", that means video input = current
                    # If "All" or "Aud", audio input = current
                    if "Vid" in msg or "All" in msg:
                        self.current_input = current
                    if "Aud" in msg or "All" in msg:
                        self.audio_input = current
                    _LOGGER.info(
                        "Switcher current input updated: video=%s, audio=%s",
                        self.current_input,
                        self.audio_input,
                    )
            # We might also catch audio gain responses like "IN3 AUD=-13", but ignoring for now.
        elif msg.startswith("V") and "QVER" in msg:
            # This looks like the full status response to the "I" command, e.g. "V3 A3 F1 QVER1.23 M6"
            parts = msg.split()
            # parts like ['V3', 'A3', 'F1', 'QVER1.23', 'M6']
            for part in parts:
                if part.startswith("V"):
                    try:
                        self.current_input = int(part[1:])
                    except:
                        pass
                elif part.startswith("A"):
                    try:
                        self.audio_input = int(part[1:])
                    except:
                        pass
                elif part.startswith("F"):
                    # F1 or F2
                    mode_val = part[1:]
                    self.auto_mode = mode_val == "2"
                elif part.startswith("QVER"):
                    # software version
                    version = part.replace("QVER", "")
                    self.device_info["sw_version"] = version
                elif part.startswith("M"):
                    # total inputs, not really needed
                    pass
            _LOGGER.info(
                "Initial status: Input %s, Mode: %s",
                self.current_input,
                "Auto" if self.auto_mode else "Manual",
            )
        elif msg.upper().startswith("C") and len(msg) >= 2:
            # "Cn" message indicating input changed via front panel (unsolicited)
            try:
                new_input = int(msg[1:])
            except ValueError:
                new_input = None
            if new_input is not None:
                self.current_input = new_input
                self.audio_input = new_input
                _LOGGER.info("Front panel changed input to %d", new_input)
        elif msg.startswith("Reconfig") or msg.startswith("RECONFIG"):
            _LOGGER.info(
                "Audio level changed via front panel (RECONFIG); consider updating audio state if tracked."
            )
            # (We could query the new audio levels here if we were tracking them.)
        elif msg.startswith("E0") or msg.startswith("E1"):
            # Error code, e.g., E06 if input change blocked by auto mode
            _LOGGER.warning("Received error response from Extron: %s", msg)
            # We can handle specific errors if needed (like auto mode conflict).
            if msg.strip() == "E06":
                # Input change was attempted in auto mode - we could toggle auto off or notify.
                _LOGGER.debug("E06: Input change rejected due to auto-switch mode.")
        else:
            _LOGGER.debug("Unhandled message from device: %r", msg)

        # Notify Home Assistant that state has updated
        dispatcher.dispatcher_send(self.hass, SIGNAL_SW6_UPDATE)

    def set_input(self, input_number: int):
        """Set the active input (1-6). If auto mode is on, this will first disable auto mode."""
        if self.auto_mode:
            _LOGGER.debug(
                "Auto mode is active, sending command to disable auto-switch before selecting input."
            )
            # Send command to set manual mode (mode = 1)
            # According to SIS: F1 sets mode to manual&#8203;:contentReference[oaicite:32]{index=32}.
            self._client.send_command("F1")
            # We optimistically update our mode state, actual confirm will come in status or not at all.
            self.auto_mode = False
        # Now send the input select command
        if 0 < input_number <= 6:
            self._client.send_command(f"{input_number}!")
        else:
            _LOGGER.error("Input number %s out of range 1-6", input_number)

    def set_auto_mode(self, enable: bool):
        """Enable or disable auto-switch mode."""
        cmd = "F2" if enable else "F1"
        self._client.send_command(cmd)
        # Assume it will succeed; update our state. We will adjust if a later status message contradicts it.
        self.auto_mode = enable
        _LOGGER.info("Set auto-switch mode: %s", "ON" if enable else "OFF")
