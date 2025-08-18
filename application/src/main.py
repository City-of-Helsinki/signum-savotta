"""
Signum labeller application
"""

import ctypes
import sys
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

    def __init__(self, stability_threshold: int = 3):
        self.current_overall_state = OverallState.NOT_READY_TO_USE
        self.state_stability_counter = {}
        self.STABILITY_THRESHOLD = stability_threshold

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

        # Apply stability check (except for critical states like battery low)
        if candidate_state == OverallState.BATTERY_LOW:
            # Battery low should be immediate
            self.current_overall_state = candidate_state
            self.state_stability_counter = {candidate_state: self.STABILITY_THRESHOLD}
        else:
            if candidate_state not in self.state_stability_counter:
                # New candidate state, reset counter
                self.state_stability_counter = {candidate_state: 1}
            else:
                self.state_stability_counter[candidate_state] += 1

            # Only change state if it's been stable for threshold iterations
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
        # Battery check always takes priority
        if battery_percent < 10:
            return OverallState.BATTERY_LOW

        error_states = {
            ReaderState.READER_ERROR,
            ReaderState.MULTIPLE_TAGS_DETECTED,
            ReaderState.UNKNOWN_TAG,
        }

        # Check if backend and registration are OK
        backend_ok = backend_client.backend_state == BackendState.BACKEND_OK
        registration_ok = (
            backend_client.registration_state == RegistrationState.REGISTRATION_SUCCEEDED
        )

        if backend_ok and registration_ok:
            # System is authorized, check for errors or readiness
            if reader_state in error_states:
                return OverallState.READY_WITH_ERROR
            elif (
                reader_state not in {ReaderState.NO_READER_CONNECTED}
                and printer_state == PrinterState.PRINTER_CONNECTED
            ):
                return OverallState.READY_TO_USE
        elif backend_client.backend_state == BackendState.BACKEND_ERROR_RESPONSE:
            # Backend error should show as ready with error if other components are OK
            if (
                registration_ok
                and reader_state not in {ReaderState.NO_READER_CONNECTED}
                and printer_state == PrinterState.PRINTER_CONNECTED
            ):
                return OverallState.READY_WITH_ERROR

        # Default to not ready
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

        # Overall state variable
        self.overall_state: OverallState = OverallState.NOT_READY_TO_USE

        # Backend client for network communication
        self.backend_client = BackendClient()

        # Configuration manager
        self.config_manager = ConfigurationManager()

        # State transition manager for debounced state transitions
        self.state_manager = StateTransitionManager(
            stability_threshold=self.config_manager.get_state_stability_threshold()
        )

        # Configure the backend client if configuration is valid
        if self.config_manager.is_valid():
            self.backend_client.configure(
                backend_url=self.config_manager.get_backend_url(),
                registration_name=self.config_manager.get_registration_name(),
                registration_key=self.config_manager.get_registration_key(),
                update_sierra_items=self.config_manager.should_update_sierra_items(),
            )
            self.backend_client.refresh_status_with_backend()

        # RFID Reader instance
        self.rfid_reader = RFIDReader()
        self.reader_state: ReaderState = ReaderState.NO_READER_CONNECTED
        self.active_item: str | None = None
        self.last_printed_tag: HelmetRfidTag | None = None

        # Printer instance
        self.printer = Printer()
        self.printer_state: PrinterState = PrinterState.NO_PRINTER_CONNECTED

        # For UI "animation" based on reader event loop iterations
        self.iteration: int = 0

        # The message to display to end user
        self.main_message: str = ""

        super().__init__()

        self.timer = QTimer()
        self.timer.setInterval(self.config_manager.get_ui_update_interval())
        self.timer.timeout.connect(self.reader_loop)
        self.timer.start()

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
        # Store configuration using the configuration manager
        success = self.config_manager.store_configuration(
            backend_url, registration_name, registration_key
        )

        if success:
            # Update backend client configuration
            self.backend_client.configure(
                backend_url=backend_url,
                registration_name=registration_name,
                registration_key=registration_key,
                update_sierra_items=self.backend_client.update_sierra_items,
            )

    def reader_loop(self):
        """
        Application event loop
        """

        self.configuration_state_sig.emit(self.config_manager.get_state().name)

        # Laptop battery
        battery = psutil.sensors_battery()
        if battery:
            self.batterycharging_sig.emit(battery.power_plugged)
            self.batterypercentage_sig.emit(battery.percent)

        # Emit just to inform that the reader loop is on
        if self.iteration < self.config_manager.get_backend_refresh_interval():
            self.iteration = self.iteration + 1
        else:
            # Every Nth iteration (configurable) we push client status to backend
            # and check connectivity and authorization. Any connectivity errors are also cleared
            self.backend_client.refresh_status_with_backend()
            self.iteration = 1
        self.iteration_sig.emit(self.iteration)

        # Update printer discovery
        printer_result = self.printer.discover_printer()
        self.printer_state = printer_result.state

        # Update RFID reader state and get result
        rfid_result = self.rfid_reader.update()
        self.reader_state = rfid_result.state

        # Handle RFID reader results that require backend coordination
        if rfid_result.state == ReaderState.TAG_PARSED and rfid_result.tag:
            # Check if we need to fetch item data from backend
            if (
                self.active_item is None
                or rfid_result.tag.primary_item_identifier != self.active_item.get("barcode")
            ):
                self.active_item = self.backend_client.get_item_data(
                    rfid_result.tag.primary_item_identifier
                )

            if self.active_item:
                # Generate item display message
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
                    owner_library_isil=rfid_result.tag.owner_library_isil,
                    classification=self.active_item.get("classification"),
                    shelfmark=self.active_item.get("shelfmark"),
                )

                # Handle printing
                if (
                    rfid_result.tag != self.last_printed_tag
                    and self.overall_state == OverallState.READY_TO_USE
                    and self.active_item is not None
                ):
                    # Use the printer class to handle signum printing
                    print_success = self.printer.print_signum(
                        classification=self.active_item["classification"],
                        shelfmark=self.active_item["shelfmark"],
                        material_code=self.active_item.get("material_code"),
                    )

                    if print_success:
                        # Update Sierra item if configured to do so
                        self.backend_client.update_sierra_item(
                            self.active_item.get("item_record_id")
                        )

                self.last_printed_tag = rfid_result.tag
            else:
                # Handle case where item data couldn't be retrieved
                if self.backend_client.backend_state == BackendState.BACKEND_EMPTY_RESPONSE:
                    sentry_sdk.capture_message("Item not found in system")
                    self.main_message = ERROR_MESSAGE_TEMPLATE.format(error=ITEM_NOT_FOUND)
                else:
                    sentry_sdk.capture_message("Item not found in system")
                    self.main_message = ERROR_MESSAGE_TEMPLATE.format(error=ERROR_FETCHING_ITEM)

        # Clear item data when not in tag reading states
        elif rfid_result.state not in [ReaderState.SINGLE_TAG_READ, ReaderState.TAG_PARSED]:
            self.active_item = None
            self.last_printed_tag = None

        # Determine overall state using StateTransitionManager with debouncing
        self.overall_state = self.state_manager.update_overall_state(
            self.backend_client, self.reader_state, self.printer_state, battery.percent
        )

        # Get status info from backend client
        status_info = self.backend_client.get_status_info()

        # Emit print station registration name
        self.registration_name_sig.emit(f"{self.backend_client.registration_name}")

        # Emit state signals to update the UI
        self.backend_state_sig.emit(f"{self.backend_client.backend_state.name}")
        self.registration_state_sig.emit(f"{self.backend_client.registration_state.name}")
        self.reader_state_sig.emit(f"{self.reader_state.name}")
        self.printer_state_sig.emit(f"{self.printer_state.name}")
        self.overall_state_sig.emit(f"{self.overall_state.name}")

        # Emit status messages
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
            if self.reader_state == ReaderState.NO_READER_CONNECTED:
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
            self.reader_state == ReaderState.SINGLE_TAG_READ
            or self.reader_state == ReaderState.TAG_PARSED
        ) and rfid_result.tag is not None:
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
