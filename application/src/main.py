"""
Signum labeller application
"""

import ctypes
import sys
import time
from enum import Enum

import assets_rc  # noqa: F401
import psutil
import sentry_sdk
from backend_client import BackendClient, BackendState, RegistrationState
from config_manager import ConfigurationManager
from helmet_rfid_tag import HelmetRfidTag
from printer import Printer, PrinterState
from PySide6.QtCore import QObject, QTimer, Signal, Slot
from PySide6.QtGui import QGuiApplication, QIcon, QPixmap
from PySide6.QtQml import QQmlApplicationEngine
from rfid_reader import ReaderState, RFIDReader
from ui_messages import (
    BACKEND_EMPTY_RESPONSE_MESSAGE,
    BACKEND_ERROR_MESSAGE,
    BACKEND_STATUS_ERROR,
    BACKEND_STATUS_NO_CONNECTION,
    BACKEND_STATUS_OK,
    BATTERY_LOW_MESSAGE,
    ERROR_FETCHING_ITEM,
    ERROR_MESSAGE_TEMPLATE,
    FIX_CHECK_NETWORK,
    FIX_CONNECT_PRINTER,
    FIX_CONNECT_RFID,
    FIX_REPORT_BACKEND_ERROR,
    FIX_REQUEST_AUTHORIZATION,
    ITEM_DATA_MESSAGE_TEMPLATE,
    ITEM_NOT_FOUND,
    MULTIPLE_TAGS_ERROR,
    NOT_READY_HEADER,
    NOT_READY_INSTRUCTIONS_HEADER,
    NOT_READY_INSTRUCTIONS_TEMPLATE,
    NOT_READY_STATUS_TEMPLATE,
    READER_ERROR_MESSAGE,
    READER_STATUS_TEMPLATE,
    READY_TO_PRINT_MESSAGE,
    REGISTRATION_STATUS_FAILED_TEMPLATE,
    REGISTRATION_STATUS_OK_TEMPLATE,
    STATUS_BACKEND_ERROR,
    STATUS_BACKEND_NO_RESPONSE,
    STATUS_BACKEND_WORKING,
    STATUS_NO_AUTHORIZATION,
    STATUS_PRINTER_FOUND,
    STATUS_PRINTER_NOT_FOUND,
    STATUS_RFID_CONNECTED,
    STATUS_RFID_NOT_CONNECTED,
    STATUS_STATION_AUTHORIZED,
    UNKNOWN_TAG_ERROR,
    get_error_status_text,
)

# Set app user model ID in so that application icon is visible in Windows taskbar
myappid = "helsinki.signumsavotta.application.1"
ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)


def _parse_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("true", "1", "yes", "on")


class OverallState(Enum):
    """
    Application overall states.
    """

    NOT_READY_TO_USE = 0
    READY_TO_USE = 1
    READY_WITH_ERROR = 2
    BATTERY_LOW = 3


class StateTransitionManager:
    """
    Manages application overall state transitions with debouncing to prevent UI flickering.
    Requires multiple consistent readings before changing states.
    """

    def __init__(self, stability_threshold: int = 3, barcode_only: bool = False):
        self.current_overall_state = OverallState.NOT_READY_TO_USE
        self.state_stability_counter = {}
        self.STABILITY_THRESHOLD = stability_threshold
        self.barcode_only = barcode_only

    def update_overall_state(
        self, backend_client, reader_state, printer_state, battery_percent
    ) -> OverallState:
        """
        Update overall state based on component states with debouncing.

        Args:
            backend_client: BackendClient instance
            reader_state: Current ReaderState
            printer_state: Current PrinterState
            battery_percent: Current battery percentage

        Returns:
            OverallState: The stable overall state
        """
        candidate_state = self._determine_candidate_state(
            backend_client, reader_state, printer_state, battery_percent
        )

        if candidate_state == OverallState.BATTERY_LOW:
            self.current_overall_state = candidate_state
            self.state_stability_counter = {candidate_state: self.STABILITY_THRESHOLD}
        else:
            if candidate_state not in self.state_stability_counter:
                self.state_stability_counter = {candidate_state: 1}
            else:
                self.state_stability_counter[candidate_state] += 1

            if self.state_stability_counter[candidate_state] >= self.STABILITY_THRESHOLD:
                self.current_overall_state = candidate_state

        return self.current_overall_state

    def _determine_candidate_state(
        self, backend_client, reader_state, printer_state, battery_percent
    ) -> OverallState:
        """
        Determine what the overall state should be based on current component states.

        Args:
            backend_client: BackendClient instance
            reader_state: Current ReaderState
            printer_state: Current PrinterState
            battery_percent: Current battery percentage

        Returns:
            OverallState: The candidate overall state
        """
        if battery_percent < 10:
            return OverallState.BATTERY_LOW

        error_states = {
            ReaderState.READER_ERROR,
            ReaderState.MULTIPLE_TAGS_DETECTED,
            ReaderState.UNKNOWN_TAG,
        }

        backend_ok = backend_client.backend_state == BackendState.BACKEND_OK
        registration_ok = (
            backend_client.registration_state == RegistrationState.REGISTRATION_SUCCEEDED
        )

        reader_available = self.barcode_only or reader_state != ReaderState.NO_READER_CONNECTED

        if backend_ok and registration_ok:
            if reader_state in error_states:
                return OverallState.READY_WITH_ERROR
            elif reader_available and printer_state == PrinterState.PRINTER_CONNECTED:
                return OverallState.READY_TO_USE
        elif backend_client.backend_state == BackendState.BACKEND_ERROR_RESPONSE:
            if (
                registration_ok
                and reader_available
                and printer_state == PrinterState.PRINTER_CONNECTED
            ):
                return OverallState.READY_WITH_ERROR

        return OverallState.NOT_READY_TO_USE


class Backend(QObject):
    """
    Labelling application backend which contains event loop and logic.
    Exposes and emits Qt signals to the Qt Quick UI.
    """

    registration_name_sig = Signal(str, arguments=["string"])
    backend_state_sig = Signal(str, arguments=["string"])
    configuration_state_sig = Signal(str, arguments=["string"])
    registration_state_sig = Signal(str, arguments=["string"])
    reader_state_sig = Signal(str, arguments=["string"])
    printer_state_sig = Signal(str, arguments=["string"])
    overall_state_sig = Signal(str, arguments=["string"])
    message_sig = Signal(str, arguments=["string"])
    backend_statustext_sig = Signal(str, arguments=["string"])
    registration_statustext_sig = Signal(str, arguments=["string"])
    reader_statustext_sig = Signal(str, arguments=["string"])
    printer_statustext_sig = Signal(str, arguments=["string"])
    iteration_sig = Signal(int, arguments=["int"])
    batterypercentage_sig = Signal(int, arguments=["int"])
    batterycharging_sig = Signal(bool, arguments=["bool"])

    def __init__(self):

        self.overall_state: OverallState = OverallState.NOT_READY_TO_USE

        self.backend_client = BackendClient()

        self.config_manager = ConfigurationManager()

        self.barcode_only = self.config_manager.get(
            "barcode", "barcode_only", _parse_bool
        )
        self.barcode_min_length = self.config_manager.get(
            "barcode", "min_length", int
        )

        self.state_manager = StateTransitionManager(
            stability_threshold=self.config_manager.get("ui", "state_stability_threshold", int),
            barcode_only=self.barcode_only,
        )

        if self.config_manager.is_valid():
            self.backend_client.configure(
                backend_url=self.config_manager.get("backend", "url"),
                registration_name=self.config_manager.get("registration", "name"),
                registration_key=self.config_manager.get("registration", "key"),
                update_sierra_items=self.config_manager.get("backend", "update_sierra_items"),
            )
            self.backend_client.refresh_status_with_backend()

        self.rfid_reader = RFIDReader()
        self.reader_state: ReaderState = ReaderState.NO_READER_CONNECTED
        self.active_item: dict | None = None
        self.last_printed_tag: HelmetRfidTag | None = None
        # Monotonic deadline (in seconds) until which a barcode-scanned item
        # remains displayed. The reader_loop polls every 100 ms and otherwise
        # wipes active_item / overwrites the message whenever no RFID tag is
        # present — which is always true in barcode-only mode.
        self._barcode_display_until: float = 0.0
        self._barcode_display_duration_s: float = 5.0

        self.printer = Printer(self.config_manager)

        self.printer_state: PrinterState = PrinterState.NO_PRINTER_CONNECTED

        self.iteration: int = 0

        self.main_message: str = ""

        super().__init__()

        self.timer = QTimer()
        self.timer.setInterval(self.config_manager.get("ui", "update_interval_ms", int))
        self.timer.timeout.connect(self.reader_loop)
        self.timer.start()

    @Slot(result=int)
    def barcodeMinLength(self) -> int:
        """
        Expose the configured minimum barcode length to QML so the capture
        Item can ignore short, partial scans.
        """
        return self.barcode_min_length

    @Slot(str, str, str)
    def storeConfiguration(self, backend_url: str, registration_name: str, registration_key: str):
        """
        Stores configuration information in a config.ini file.
        Preserves existing configuration values that are not being updated.

        Args:
            backend_url (str): The backend URL
            registration_name (str): The print station name.
            registration_key (str): The associated registration key.
        """
        success = self.config_manager.store_configuration(
            backend_url, registration_name, registration_key
        )

        if success:
            self.backend_client.configure(
                backend_url=backend_url,
                registration_name=registration_name,
                registration_key=registration_key,
                update_sierra_items=self.backend_client.update_sierra_items,
            )

    @Slot(str)
    def submitBarcode(self, barcode: str):
        """
        Receive a complete barcode buffered and submitted by the QML-side
        capture Item on the Enter terminator. Looks up the item and prints
        in the same way as an RFID tag read.
        """
        barcode = barcode.strip()
        if len(barcode) < self.barcode_min_length:
            return
        self._process_identifier(barcode, source_tag=None)
        # Keep the item display visible for a short window so the next
        # reader_loop tick (which has no RFID tag to report) does not
        # immediately overwrite it with READY_TO_PRINT_MESSAGE.
        self._barcode_display_until = (
            time.monotonic() + self._barcode_display_duration_s
        )

    def _process_identifier(
        self, identifier: str, source_tag: HelmetRfidTag | None = None
    ):
        """
        Look up an item by its barcode/identifier, emit a display message,
        and trigger a deferred print when the application is ready.

        :param identifier: primary item identifier (barcode string)
        :param source_tag: the RFID tag that produced the identifier, or
            ``None`` when the identifier came from a barcode scanner. The
            scanner path treats every scan as a fresh print request; the
            RFID path suppresses reprints while the same tag is still on
            the reader.
        """
        if (
            self.active_item is None
            or identifier != self.active_item.get("barcode")
        ):
            self.active_item = self.backend_client.get_item_data(identifier)

        if self.active_item:
            self.main_message = ITEM_DATA_MESSAGE_TEMPLATE.format(
                best_title=self.active_item.get("best_title"),
                best_author=(
                    self.active_item.get("best_author")
                    if self.active_item.get("best_author")
                    else ""
                ),
                material_name=self.active_item.get("material_name"),
                item_type_name=self.active_item.get("item_type_name"),
                barcode=self.active_item.get("barcode"),
                owner_library_isil=(
                    source_tag.owner_library_isil if source_tag else ""
                ),
                classification=self.active_item.get("classification"),
                shelfmark=self.active_item.get("shelfmark"),
            )
            self.message_sig.emit(f"{self.main_message}")

            is_new_for_print = (
                source_tag is None or source_tag != self.last_printed_tag
            )
            if (
                is_new_for_print
                and self.overall_state == OverallState.READY_TO_USE
            ):
                # Defer the print to the next event-loop iteration so the
                # UI has a chance to repaint the item info from the just-
                # emitted message_sig before the (slow on PT-series)
                # print_signum blocks the main thread. Capture the values
                # by closure since active_item could change before the
                # deferred call fires.
                classification = self.active_item["classification"]
                shelfmark = self.active_item["shelfmark"]
                material_code = self.active_item.get("material_code")
                item_record_id = self.active_item.get("item_record_id")

                def _deferred_print():
                    if self.printer.print_signum(
                        classification=classification,
                        shelfmark=shelfmark,
                        material_code=material_code,
                    ):
                        self.backend_client.update_sierra_item(item_record_id)

                QTimer.singleShot(0, _deferred_print)
            if source_tag is not None:
                self.last_printed_tag = source_tag
        else:
            if self.backend_client.backend_state == BackendState.BACKEND_EMPTY_RESPONSE:
                sentry_sdk.capture_message(f"Item not found in system: {identifier!r}")
                self.main_message = ERROR_MESSAGE_TEMPLATE.format(
                    error=f"{ITEM_NOT_FOUND} (haettu: {identifier})"
                )
            else:
                sentry_sdk.capture_message(f"Item not found in system: {identifier!r}")
                self.main_message = ERROR_MESSAGE_TEMPLATE.format(
                    error=f"{ERROR_FETCHING_ITEM} (haettu: {identifier})"
                )
            # Keep the error visible across the loop ticks that follow a
            # barcode scan instead of flashing back to "Ready to print".
            if source_tag is None:
                self.message_sig.emit(f"{self.main_message}")

    def reader_loop(self):
        """
        Application event loop
        """

        self.configuration_state_sig.emit(self.config_manager.configuration_state.name)

        battery = psutil.sensors_battery()
        if battery:
            self.batterycharging_sig.emit(battery.power_plugged)
            self.batterypercentage_sig.emit(battery.percent)

        if self.iteration < self.config_manager.get("ui", "backend_refresh_interval", int):
            self.iteration = self.iteration + 1
        else:
            self.backend_client.refresh_status_with_backend()
            self.iteration = 1
        self.iteration_sig.emit(self.iteration)

        printer_result = self.printer.discover_printer()
        self.printer_state = printer_result.state

        rfid_result = self.rfid_reader.update()
        self.reader_state = rfid_result.state

        barcode_display_active = time.monotonic() < self._barcode_display_until

        if rfid_result.state == ReaderState.TAG_PARSED and rfid_result.tag:
            self._process_identifier(
                rfid_result.tag.primary_item_identifier,
                source_tag=rfid_result.tag,
            )
        elif (
            rfid_result.state not in [ReaderState.SINGLE_TAG_READ, ReaderState.TAG_PARSED]
            and not barcode_display_active
        ):
            self.active_item = None
            self.last_printed_tag = None

        self.overall_state = self.state_manager.update_overall_state(
            self.backend_client,
            self.reader_state,
            self.printer_state,
            battery.percent if battery else "no battery",
        )

        status_info = self.backend_client.get_status_info()

        self.registration_name_sig.emit(f"{self.backend_client.registration_name}")
        self.backend_state_sig.emit(f"{self.backend_client.backend_state.name}")
        self.registration_state_sig.emit(f"{self.backend_client.registration_state.name}")
        self.reader_state_sig.emit(f"{self.reader_state.name}")
        self.printer_state_sig.emit(f"{self.printer_state.name}")
        self.overall_state_sig.emit(f"{self.overall_state.name}")

        if self.backend_client.backend_state == BackendState.BACKEND_OK:
            self.backend_statustext_sig.emit(BACKEND_STATUS_OK)
        elif self.backend_client.backend_state == BackendState.BACKEND_NOT_AVAILABLE:
            self.backend_statustext_sig.emit(BACKEND_STATUS_NO_CONNECTION)
        else:
            self.backend_statustext_sig.emit(BACKEND_STATUS_ERROR)

        if self.backend_client.registration_state == RegistrationState.REGISTRATION_SUCCEEDED:
            self.registration_statustext_sig.emit(
                REGISTRATION_STATUS_OK_TEMPLATE.format(
                    hostname=status_info["hostname"], ip_address=status_info["ip_address"]
                )
            )
        else:
            self.registration_statustext_sig.emit(
                REGISTRATION_STATUS_FAILED_TEMPLATE.format(
                    hostname=status_info["hostname"], ip_address=status_info["ip_address"]
                )
            )

        self.reader_statustext_sig.emit(READER_STATUS_TEMPLATE.format(version=rfid_result.version))

        self.printer_statustext_sig.emit(
            f"{self.printer.device['identifier']}"
            if self.printer.state == PrinterState.PRINTER_CONNECTED and self.printer.device
            else STATUS_PRINTER_NOT_FOUND.capitalize()
        )

        # Determine the main message to display on the UI. We try to formulate a message using natural language.
        if self.overall_state == OverallState.BATTERY_LOW:
            self.message_sig.emit(BATTERY_LOW_MESSAGE)
        elif self.overall_state == OverallState.NOT_READY_TO_USE:
            positives, negatives, fixes = [], [], []
            if self.backend_client.backend_state == BackendState.BACKEND_OK:
                positives.append(STATUS_BACKEND_WORKING)
            if self.backend_client.registration_state == RegistrationState.REGISTRATION_SUCCEEDED:
                positives.append(STATUS_STATION_AUTHORIZED)
            if self.reader_state is not ReaderState.NO_READER_CONNECTED:
                positives.append(STATUS_RFID_CONNECTED)
            if self.printer_state == PrinterState.PRINTER_CONNECTED:
                positives.append(STATUS_PRINTER_FOUND)
            if self.backend_client.backend_state == BackendState.BACKEND_NOT_AVAILABLE:
                negatives.append(STATUS_BACKEND_NO_RESPONSE)
                fixes.append(FIX_CHECK_NETWORK)
            elif self.backend_client.backend_state == BackendState.BACKEND_ERROR_RESPONSE:
                negatives.append(STATUS_BACKEND_ERROR)
                fixes.append(FIX_REPORT_BACKEND_ERROR)
            if self.backend_client.registration_state == RegistrationState.REGISTRATION_FAILED:
                negatives.append(STATUS_NO_AUTHORIZATION)
                if self.backend_client.backend_state is not BackendState.BACKEND_NOT_AVAILABLE:
                    fixes.append(FIX_REQUEST_AUTHORIZATION)
            if (
                self.reader_state == ReaderState.NO_READER_CONNECTED
                and not self.barcode_only
            ):
                negatives.append(STATUS_RFID_NOT_CONNECTED)
                fixes.append(FIX_CONNECT_RFID)
            if self.printer_state == PrinterState.NO_PRINTER_CONNECTED:
                negatives.append(STATUS_PRINTER_NOT_FOUND)
                fixes.append(FIX_CONNECT_PRINTER)
            self.message_sig.emit(
                (
                    NOT_READY_HEADER
                    + NOT_READY_STATUS_TEMPLATE.format(
                        status_text=get_error_status_text(positives=positives, negatives=negatives)
                    )
                    + NOT_READY_INSTRUCTIONS_HEADER
                    + NOT_READY_INSTRUCTIONS_TEMPLATE.format(fixes="\n".join(fixes))
                )
            )
        elif self.overall_state == OverallState.READY_WITH_ERROR:
            if self.reader_state == ReaderState.MULTIPLE_TAGS_DETECTED:
                self.message_sig.emit(MULTIPLE_TAGS_ERROR)
            elif self.reader_state == ReaderState.UNKNOWN_TAG:
                self.message_sig.emit(UNKNOWN_TAG_ERROR)
            elif self.backend_client.backend_state == BackendState.BACKEND_ERROR_RESPONSE:
                self.message_sig.emit(BACKEND_ERROR_MESSAGE)
            elif self.backend_client.backend_state == BackendState.BACKEND_EMPTY_RESPONSE:
                self.message_sig.emit(BACKEND_EMPTY_RESPONSE_MESSAGE)
            else:
                self.message_sig.emit(READER_ERROR_MESSAGE)
        elif (
            (
                self.reader_state == ReaderState.SINGLE_TAG_READ
                or self.reader_state == ReaderState.TAG_PARSED
            )
            and rfid_result.tag is not None
        ) or (barcode_display_active and self.main_message):
            self.message_sig.emit(f"{self.main_message}")
        else:
            self.message_sig.emit(READY_TO_PRINT_MESSAGE)


def start():
    """
    Start the application
    """
    app = QGuiApplication(sys.argv)

    iconpixmap = QPixmap(":/assets/signumsavotta.png")
    app_icon = QIcon()
    for size in [256, 128, 96, 64, 48, 32, 24, 16]:
        app_icon.addPixmap(iconpixmap.scaledToHeight(size))
    app.setWindowIcon(app_icon)

    backend = Backend()
    backend.reader_loop()

    engine = QQmlApplicationEngine()
    engine.quit.connect(app.quit)
    engine.load(":/main.qml")
    engine.rootObjects()[0].setProperty("backend", backend)

    for object in engine.rootObjects():
        if object.isWindowType():
            object.setIcon(app_icon)
            object.setTitle("Signum-savotta")
            object.requestActivate()

    sys.exit(app.exec())


if __name__ == "__main__":
    start()
