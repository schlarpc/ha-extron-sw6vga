import threading
import logging
import serial  # pyserial
from typing import Optional, Callable

from .const import DEFAULT_BAUDRATE, DEFAULT_TIMEOUT

_LOGGER = logging.getLogger(__name__)


class ExtronSerialClient:
    """Manages low-level serial/TCP communication with Extron SW6VGA."""

    def __init__(
        self, device_url: str, on_message: Optional[Callable[[str], None]] = None
    ):
        """
        Initialize the serial client.
        :param device_url: PySerial device identifier (e.g. '/dev/ttyUSB0' or 'socket://host:port').
        :param on_message: Callback to invoke with each complete message received from the device.
        """
        # If user provided a tcp:// URL, replace with socket:// for pyserial
        if device_url.startswith("tcp://"):
            # Convert to socket:// (pyserial expects socket:// for raw TCP)
            device_url = "socket://" + device_url[len("tcp://") :]
        self.device_url = device_url
        self.on_message = on_message
        self._serial = None
        self._thread = None
        self._stop_event = threading.Event()

    def connect(self):
        """Open the serial connection and start the reader thread."""
        _LOGGER.info("Connecting to Extron SW6VGA at %s", self.device_url)
        # Using pyserial's serial_for_url to handle both local and TCP
        try:
            self._serial = serial.serial_for_url(
                self.device_url, baudrate=DEFAULT_BAUDRATE, timeout=DEFAULT_TIMEOUT
            )
        except Exception as err:
            _LOGGER.error("Failed to open serial device %s: %s", self.device_url, err)
            raise
        # Start reader thread
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._read_loop, name="ExtronSW6Reader", daemon=True
        )
        self._thread.start()
        _LOGGER.debug("Serial reader thread started for %s", self.device_url)

    def _read_loop(self):
        """Background thread: read from serial and handle messages."""
        buffer = ""
        try:
            while not self._stop_event.is_set():
                # Read one byte at a time (non-blocking or with timeout) and accumulate
                ch = self._serial.read(1).decode(errors="ignore")
                if not ch:  # Timeout with no data
                    continue
                if ch in ("\r", "\n"):
                    if buffer:  # complete message ready
                        msg = buffer
                        buffer = ""
                        _LOGGER.debug("Received from device: %r", msg)
                        if self.on_message:
                            try:
                                self.on_message(msg)
                            except Exception as e:
                                _LOGGER.exception("Error in on_message callback: %s", e)
                    # if it's just an isolated CR/LF, skip adding to buffer
                else:
                    buffer += ch
        except Exception as err:
            _LOGGER.error("Error in Extron serial read loop: %s", err)
        finally:
            _LOGGER.info(
                "Extron SW6VGA reader thread terminating for %s", self.device_url
            )
            try:
                if self._serial:
                    self._serial.close()
            except Exception:
                pass

    def send_command(self, command: str):
        """Send a raw command string to the device, appending CR."""
        if not self._serial:
            _LOGGER.warning("Attempt to send command on closed connection: %s", command)
            return
        cmd_str = command + "\r"
        # Log what we send for debugging
        _LOGGER.debug("Sending to device: %r", cmd_str)
        try:
            # Ensure bytes encoding
            self._serial.write(cmd_str.encode("ascii", errors="ignore"))
        except Exception as err:
            _LOGGER.error("Failed to send command '%s': %s", command, err)
            # If write fails, we might consider reconnecting or marking disconnected
            # (For simplicity, handle higher-level in integration)

    def disconnect(self):
        """Stop the reader thread and close the connection."""
        _LOGGER.info("Disconnecting from Extron SW6VGA at %s", self.device_url)
        self._stop_event.set()
        # Wait a short moment for thread to finish
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        if self._serial:
            try:
                self._serial.close()
            except Exception as err:
                _LOGGER.debug("Error closing serial: %s", err)
        self._serial = None
        self._thread = None
