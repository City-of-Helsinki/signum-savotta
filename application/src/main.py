"""
Signum labeller application
"""

# FIXME: Split RFID reader related code to own class

import ctypes
import socket
import sys
import time
import traceback
from enum import Enum

import assets_rc  # noqa: F401
import httpx
import psutil
import serial
from brother_ql.backends.helpers import discover, send
from brother_ql.conversion import convert
from brother_ql.raster import BrotherQLRaster
from helmet_rfid_tag import HelmetRfidTag
from PIL import Image, ImageDraw, ImageFont
from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QGuiApplication, QIcon, QPixmap
from PySide6.QtQml import QQmlApplicationEngine

# Set app user model ID in so that application icon is visible in Windows taskbar
myappid = "helsinki.signumsavotta.application.1"
ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)


class Command(Enum):
    """
    Enum for RFID Serial protocol command descriptor byte.
    """

    NORM_READ_BLOCK_UID = 0xFE
    NORM_READER_VERSION = 0x11
    NORM_ISO_PASS_THROUGH = 0x14

    ADDR_QUIET = 0x01
    ADDR_READ_MULTIBLOCK = 0x02
    ADDR_WRITE_MULTIBLOCK = 0x04
    ADDR_WRITE_BLOCK = 0x05
    ADDR_WRITE_AND_LOCK_BLOCK = 0x07
    ADDR_LOCK_BLOCK = 0x08

    ADDR_GET_AFI = 0x0A
    ADDR_WRITE_AFI = 0x09
    ADDR_LOCK_AFI = 0x06

    ADDR_CHECK_EAS = 0x03
    ADDR_EAS_CONTROL = 0x0C

    ADDR_GET_DSFID = 0x0F
    ADDR_WRITE_DSFID = 0x0F
    ADDR_LOCK_DSFID = 0x0F

    ADDR_TAG_INFO = 0x0F


def get_font_size_for_text(text, initial_size, font_path, target_height):
    """
    get_font_size_for_text Fits font size to target height for a text string in given font.

    :param text: the text to be fitted
    :param initial_size: known font size in which the string in the given font will fit the target height
    :param font_path: path to the font to use
    :param target_height: target height in pixels
    :return: ImageFont font The font which will fit, tuple[float, float, float, float] bbox
        The bounding box, height float the height of the text in pixels
    """
    font_size = initial_size
    font = ImageFont.truetype(font_path, font_size)
    bbox = font.getbbox(text)
    height = bbox[3] - bbox[1]

    while height < target_height:
        font_size += 1
        font = ImageFont.truetype(font_path, font_size)
        bbox = font.getbbox(text)
        height = bbox[3] - bbox[1]

    return font, bbox, height


def create_signum(classification, shelfmark, font_path, minimum_font_height, width, height):
    """
    get_font_size_for_text Creates a signum image for printing

    :param classification: the classification (in YKL)
    :param shelfmark: three letter word for alphabetical sorting
    :param font_path: path to the font to use
    :param minimum_font_height: minimum font size to use (text will use all the space it can get)
    :param width: width of the signum in pixels. Note that this has to correspond to brother-ql continous roll widths
    :param width: height of the signum in pixels. The minimum value is 42 which corresponds to 9mm.
        Values less than that are considered to be CD case signums which will result in additional blank space added.
    :return: Image the signum image
    """

    # Standard label height is 42 pixels (9 mm) which is also the minumum height for brother-ql cutting unit.
    # Signums labels with maximum label text of 6mm height are used in CD jewel cases and digipacks.
    # CD signum labels are printed with extra blank space above and below the signum.
    # The label is wrapped around the case. This ensures that the label adhesive works properly.
    im_height = height
    if height < 42:
        im_height = height * 5

    image = Image.new("RGB", (width, im_height), color="white")
    draw = ImageDraw.Draw(image)

    classification_font, classification_bbox, classification_height = get_font_size_for_text(
        classification, minimum_font_height, font_path, height
    )
    shelfmark_font, shelfmark_bbox, shelfmark_height = get_font_size_for_text(
        shelfmark, minimum_font_height, font_path, height
    )

    shelfmark_position = (
        width - draw.textlength(shelfmark, font=shelfmark_font),
        (im_height - shelfmark_height) / 2 - shelfmark_bbox[1],
    )
    classification_position = (0, (im_height - classification_height) / 2 - classification_bbox[1])

    draw.text(classification_position, classification, fill="black", font=classification_font)
    draw.text(shelfmark_position, shelfmark, fill="black", font=shelfmark_font)

    return image


def build_command_hex(command_code, data):
    """
    build_command_hex Builds a command to be sent to Bibliotheca/3M Model 210 RFID reader

    :param command_code: command code as two byte hexadecimal string (see inline emun Class Command)
    :param data: string the data to be sent as string containing hex representation of the command parameters
    :return: string the command as hex string
    """

    length = len(bytes.fromhex(f"{command_code:02X}{data}{0:04X}"))
    payload = f"{length:04X}{command_code:02X}{data}"
    return f"D6{payload}{crc_ccitt(bytes.fromhex(payload)):04X}"


def crc_ccitt(data):
    """
    crc_ccitt Calculates a CCITT CRC checksum for a given string

    :param data: bytes the data for which the checksum is to be calculated for
    :return: 4 byte CCITT CRC checksum
    """

    preset = 0xFFFF
    polynomial = 0x1021
    crc = preset
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = (crc << 1) ^ polynomial
            else:
                crc <<= 1
            crc &= 0xFFFF
    return crc ^ preset


# FIXME: Implement checksum error checking
# FIXME: Return corresponding dataclass instead
def parseReadVersionResponse(data):
    """
    parseReadVersionResponse parses a Version response from reader

    :param data: bytes the data to be parsed
    :return: dict the parsed data
    """
    try:
        return {
            "vendor": "3M" if data[6] == 5 else "Unknown",
            "major_value": data[7],
            "minor_value": data[8],
            "build_version": data[9],
        }
    except Exception:
        return None


# FIXME: Implement checksum error checking
# FIXME: Return corresponding dataclass instead
def parseReadBlockUIDResponse(data):
    """
    parseReadVersionResponse parses ReadBlockUID Response response from reader

    :param data: bytes the data to be parsed
    :return: dict the parsed data
    """
    try:
        num_tags = data[7]
        tags = []
        for i in range(num_tags):
            tags.append({"dsfid": data[8 + i * 8], "address": data[9 + i * 8 : 17 + i * 8]})

        return {
            "errorcode": data[4],
            "afi": data[5],
            "response_options": data[6],
            "num_tags": num_tags,
            "tags": tags,
        }
    except Exception:
        return None


# FIXME: Implement checksum error checking
# FIXME: Return corresponding dataclass instead
def parseReadMultiblockResponse(data):
    """
    parseReadMultiblockResponse parses ReadMultiblock Response response from reader

    :param data: bytes the data to be parsed
    :return: dict the parsed data
    """
    try:
        data_blocks = bytes(data[15:47])
        resp = {
            "command_code": f"{data[3]:02X}",
            "error_code": f"{data[4]:02X}",
            "address": data[5:13].hex(),
            "start_block": f"{data[13]:02X}",
            "block_count": f"{data[14]:02X}",
            "raw_blocks": data[15:47],
            "checksum_match": False,
        }
        if (
            bytes.fromhex(
                build_command_hex(
                    Command.ADDR_READ_MULTIBLOCK.value,
                    (
                        f"{resp['error_code']}{resp['address']}"
                        f"{resp['start_block']}{resp['block_count']}"
                        f"{data_blocks.hex()}"
                    ),
                )
            ).hex()
            == data.hex()
        ):
            resp["checksum_match"] = True
        return resp
    except Exception:
        return None


def join_with_and(items, last_separator="ja"):
    """
    join_with_and takes a list of items, joins them with comma
        except the last one which is joined with last_separator parameter.
        If the last separator is "eikä" (nor), it also replaces any negatives.

    :parameter items: array the items to be joined
    :parameter last_separator:
    :return: str the resulting string

    """
    if not items:
        return ""
    elif len(items) == 1:
        return items[0]
    else:
        if last_separator == "eikä":
            last = items[-1].replace(" ei ", " ")
        else:
            last = items[-1]
        return ", ".join(items[:-1]) + f" {last_separator} " + last


class OverallState(Enum):
    """
    Application overall states.
    """

    NOT_READY_TO_USE = 0
    READY_TO_USE = 1
    READY_WITH_ERROR = 2
    BATTERY_LOW = 3


class BackendState(Enum):
    """
    Backend states.
    """

    NO_BACKEND_RESPONSE = 0
    BACKEND_OK = 1
    BACKEND_ERROR_RESPONSE = 2
    BACKEND_EMPTY_RESPONSE = 3


class RegistrationState(Enum):
    """
    Application registration states.
    """

    REGISTRATION_FAILED = 0
    REGISTRATION_SUCCEEDED = 1


class ReaderState(Enum):
    """
    RFID reader states.
    """

    NO_READER_CONNECTED = 0
    READER_CONNECTED = 1
    SINGLE_TAG_DETECTED = 2
    MULTIPLE_TAGS_DETECTED = 3
    SINGLE_TAG_READ = 4
    PRINT_TAG = 5
    READER_ERROR = 6
    UNKNOWN_TAG = 7


class PrinterState(Enum):
    """
    Label printer states.
    """

    NO_PRINTER_CONNECTED = 0
    PRINTER_CONNECTED = 1


# FIXME: The response parsing should be dynamic rather than comparing to static responses.
RESPONSE_EMPTY = None
RESPONSE_READER_READY_1 = bytes.fromhex("d500090400110a05021b972a")
RESPONSE_READER_READY_2 = bytes.fromhex("d500090400110a050119e23b")
RESPONSE_NO_TAG_DETECTED = bytes.fromhex("d60007fe00000700af19")
RESPONSE_SINGLE_TAG_DETECTED = bytes.fromhex("d60007fe0000000126af")


class Backend(QObject):
    """
    Labelling application backend which contains event loop and logic.
    Exposes and emits Qt signals to the Qt Quick UI.
    """

    # FIXME: Load these from configuration file
    print_station_registration_name = "Kannelmäki, Malminkartano, Pitäjänmäki [1]"
    print_station_registration_key = ""

    # Client internal IP address
    internal_hostname = socket.gethostname()
    internal_ip_address = None

    # Signals for updating the UI
    print_station_registration_name_sig = Signal(str, arguments=["string"])
    backend_state_sig = Signal(str, arguments=["string"])
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

    # Overall state initialization
    overall_state = OverallState.NOT_READY_TO_USE

    # Backend initial state variables
    backend_state = BackendState.BACKEND_OK

    # Registration initial state variables
    registration_state = RegistrationState.REGISTRATION_SUCCEEDED

    # Reader intial state variables
    reader_version = None
    reader_state = ReaderState.NO_READER_CONNECTED
    active_address = None
    active_tag = None
    active_item = None
    last_printed_tag = None
    serial_port_number = 1
    serial_port = None

    # Printer initial state variables
    printer_state = PrinterState.NO_PRINTER_CONNECTED
    printer = None
    printer_identifier = None

    # Timing values FIXME: Load from configuration file
    ui_interval = 200
    reader_wait = 0.1

    # For UI "animation" based on reader event loop iterations
    iteration = 0

    # The message to display to end user
    item_data_message = ""

    @classmethod
    def get_internal_ip(cls) -> str | None:
        """
        Returns the internal IP address of the interface used for outbound connections.
        This is determined by creating a UDP socket to a public IP (e.g., 8.8.8.8).
        """
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("8.8.8.8", 80))
                return s.getsockname()[0]
        except Exception:
            return None

    def refresh_status_with_backend(self):
        self.internal_hostname = socket.gethostname()
        self.internal_ip_address = self.__class__.get_internal_ip()
        try:
            data = {
                "internal_hostname": f"{self.internal_hostname}",
                "internal_ip_address": f"{self.internal_ip_address}",
            }
            # FIXME: Move hardcoded configuration to config file
            response = httpx.post(
                "http://127.0.0.1:8000/status/",
                data=data,
                headers={
                    "x-api-key": self.print_station_registration_key,
                },
            )
            response.raise_for_status()
            self.backend_state = BackendState.BACKEND_OK
            self.registration_state = RegistrationState.REGISTRATION_SUCCEEDED
        except httpx.RequestError:
            # Backend had a protocol level error
            self.backend_state = BackendState.NO_BACKEND_RESPONSE
            self.registration_state = RegistrationState.REGISTRATION_FAILED
        except httpx.HTTPStatusError:
            # Backend did respond, but the response status was either 4xx or 5xx
            self.backend_state = BackendState.BACKEND_ERROR_RESPONSE
            self.registration_state = RegistrationState.REGISTRATION_FAILED

    def __init__(self):
        super().__init__()
        self.refresh_status_with_backend()
        self.timer = QTimer()
        self.timer.setInterval(self.ui_interval)
        self.timer.timeout.connect(self.reader_loop)
        self.timer.start()

    def send_data(self, data):
        """
        send_data sends data to the autoconfigured serial port

        :parameter data: bytes the data to send
        """
        self.serial_port.write(data)

    def read_data(self) -> bytes | None:
        """
        send_data reads data from the autoconfigured serial port

        :return: bytes the read data
        """
        if self.serial_port.in_waiting > 0:
            data = self.serial_port.read_all()
            return data
        return None

    # FIXME: The reader event loop is also the UI event loop. Separate for clarity.
    def reader_loop(self):
        """
        Application event loop
        """

        # Store the previous reader state for use in determining the overall status.
        # Solution for preventing read error scenarios from causing flickering in the UI
        previousReaderState = self.reader_state

        # Laptop battery
        battery = psutil.sensors_battery()
        if battery:
            self.batterycharging_sig.emit(battery.power_plugged)
            self.batterypercentage_sig.emit(battery.percent)

        # Emit just to inform that the reader loop is on
        if self.iteration < 10:
            self.iteration = self.iteration + 1
        else:
            # Every 10th iteration we push client status to backend and check connectivity and authorization
            # Any connectivity errors are also cleared
            self.refresh_status_with_backend()
            self.iteration = 1
        self.iteration_sig.emit(self.iteration)

        # Autoconfigure printer
        devices = discover(backend_identifier="pyusb")
        if not devices:
            self.printer_state = PrinterState.NO_PRINTER_CONNECTED
        else:
            self.printer_state = PrinterState.PRINTER_CONNECTED
            self.printer = devices[0]

        try:
            match self.reader_state:
                case ReaderState.NO_READER_CONNECTED:
                    if self.serial_port is None:
                        # Autoconfigure serial port
                        # FIXME: Fix Windows-only solution for cross-platform use
                        try:
                            self.serial_port = serial.Serial(
                                port=f"COM{self.serial_port_number}", baudrate=19200, timeout=1
                            )
                        except serial.SerialException:
                            if self.serial_port is not None:
                                self.serial_port.close()
                            self.serial_port = None
                            if self.serial_port_number < 10:
                                self.serial_port_number += 1
                            else:
                                self.serial_port_number = 1
                    else:
                        # Initialize the reader.
                        # For some reason, this command needs to be read from the serial interface immediately.
                        # Any delay between send and read will cause errors.
                        self.send_data(bytes.fromhex("D5 00 05 04 00 11 8C 66"))
                        response = self.read_data()
                        if (
                            response == RESPONSE_READER_READY_1
                            or response == RESPONSE_READER_READY_2
                        ):
                            # 3M Documentation does not say anything about this command
                            # Found via reverse engineering
                            self.send_data(bytes.fromhex("d60010130601000200030004000b000a00fdbf"))
                            time.sleep(self.reader_wait)
                            self.read_data()
                            # Get reader version
                            self.send_data(
                                bytes.fromhex(
                                    build_command_hex(Command.NORM_READER_VERSION.value, "")
                                )
                            )
                            time.sleep(self.reader_wait)
                            ver = parseReadVersionResponse(self.read_data())
                            self.reader_version = (
                                f"{ver['vendor']} {ver['major_value']}."
                                f"{ver['minor_value']}.{ver['build_version']}"
                            )
                            self.reader_state = ReaderState.READER_CONNECTED
                        else:
                            if response is not None:
                                # This branch will handle cases where the reader is responding with READ_BLOCK_UID
                                # and the response from the reader takes longer than the configured wait time
                                self.reader_state = ReaderState.READER_CONNECTED
                            else:
                                self.reader_state = ReaderState.NO_READER_CONNECTED

                case (
                    ReaderState.READER_CONNECTED
                    | ReaderState.MULTIPLE_TAGS_DETECTED
                    | ReaderState.READER_ERROR
                    | ReaderState.UNKNOWN_TAG
                ):
                    cmd = build_command_hex(Command.NORM_READ_BLOCK_UID.value, "0007")
                    self.send_data(bytes.fromhex(cmd))
                    time.sleep(self.reader_wait)
                    response = self.read_data()
                    if response != RESPONSE_EMPTY:
                        # FIXME: implement logic to handle checksum errors once that's implemented
                        uid_res = parseReadBlockUIDResponse(response)
                        if uid_res is not None:
                            if uid_res["num_tags"] == 1 and uid_res["afi"] == 0:
                                self.active_address = uid_res["tags"][0]["address"].hex()
                                self.last_printed_tag = None
                                self.reader_state = ReaderState.SINGLE_TAG_READ
                            elif uid_res["num_tags"] > 1:
                                self.active_address = None
                                self.active_tag = None
                                self.last_printed_tag = None
                                self.reader_state = ReaderState.MULTIPLE_TAGS_DETECTED
                            else:
                                self.active_address = None
                                self.active_tag = None
                                self.last_printed_tag = None
                                self.reader_state = ReaderState.READER_CONNECTED
                        else:
                            # The reader responds slowly
                            # This means that the response to the command is available at next loop iteration
                            # We handle this case simply by dropping to READER_CONNECTED
                            self.active_address = None
                            self.active_tag = None
                            self.last_printed_tag = None
                            self.reader_state = ReaderState.READER_CONNECTED
                    else:
                        self.active_address = None
                        self.active_tag = None
                        self.last_printed_tag = None
                        self.reader_state = ReaderState.NO_READER_CONNECTED

                case ReaderState.SINGLE_TAG_READ:
                    cmd = build_command_hex(
                        Command.ADDR_READ_MULTIBLOCK.value, f"{self.active_address}00080c"
                    )
                    self.send_data(bytes.fromhex(cmd))
                    time.sleep(self.reader_wait)
                    resp = self.read_data()
                    try:
                        response = parseReadMultiblockResponse(resp)
                        if response["checksum_match"]:
                            helmet_rfid_tag = HelmetRfidTag(response["raw_blocks"])
                            if helmet_rfid_tag.welformed_data:
                                self.active_tag = helmet_rfid_tag
                                try:
                                    if (
                                        self.active_item is None
                                        or self.active_tag.primary_item_identifier
                                        != self.active_item.get("barcode")
                                    ):
                                        # FIXME: Move hardcoded configuration to config file
                                        response = httpx.get(
                                            f"http://127.0.0.1:8000/itemdata/{helmet_rfid_tag.primary_item_identifier}"
                                        )
                                        response.raise_for_status()
                                        self.active_item = response.json()

                                    msg = (
                                        "<p>"
                                        f"<h2>{self.active_item.get("best_title")}</h2>"
                                        f"<h3>{self.active_item.get("best_author")
                                               if self.active_item.get("best_author")
                                               else ""}</h3>"
                                        "</p><p>"
                                        "<table>"
                                        "<tr><th align='left'>Materiaali</th><td width=30>&nbsp;</td>"
                                        f"<td>{self.active_item.get("material_name")}</td></tr>"
                                        "<tr><th align='left'>Nidetyyppi</th><td width=10></td>"
                                        f"<td>{self.active_item.get("item_type_name")}</td></tr>"
                                        "<tr><th align='left'>Viivakoodi</th><td width=10></td>"
                                        f"<td>{self.active_item.get("barcode")}</td></tr>"
                                        "<tr><th align='left'>RFID ISIL</th><td width=10'></td>"
                                        f"<td>{helmet_rfid_tag.owner_library_isil}</td></tr>"
                                        "<tr><th>&nbsp;</th><td width=30>&nbsp;</td><td width=30>&nbsp;</td></tr>"
                                        "<tr><th align='left'>Luokitus</th><td width=10p></td>"
                                        f"<td>{self.active_item.get("classification")}</td></tr>"
                                        "<tr><th align='left'>Pääsana</th><td width=10></td>"
                                        f"<td>{self.active_item.get("shelfmark")}</td></tr>"
                                        "</table>"
                                        "</p>"
                                    )
                                    self.item_data_message = msg
                                    self.reader_state = ReaderState.PRINT_TAG
                                except ValueError:
                                    # Response was missing required data fields
                                    self.reader_state = ReaderState.READER_CONNECTED
                                    self.backend_state = BackendState.BACKEND_ERROR_RESPONSE
                                    self.active_item = None
                                except httpx.RequestError:
                                    # Backend had a protocol level error
                                    self.reader_state = ReaderState.READER_CONNECTED
                                    self.backend_state = BackendState.NO_BACKEND_RESPONSE
                                    self.active_item = None
                                except httpx.HTTPStatusError as e:
                                    # Backend did respond, but the response status was either 4xx or 5xx
                                    self.reader_state = ReaderState.READER_CONNECTED
                                    if e.response.status_code == 404:
                                        self.backend_state = BackendState.BACKEND_EMPTY_RESPONSE
                                    else:
                                        self.backend_state = BackendState.BACKEND_ERROR_RESPONSE
                                    self.active_item = None
                                    self.item_data_message = "<p>" f"<b>Virhe: {e}</b>" "</p>"
                                except Exception:
                                    # Error catchall
                                    self.reader_state = ReaderState.READER_CONNECTED
                                    self.backend_state = BackendState.BACKEND_ERROR_RESPONSE
                                    self.active_item = None
                            else:
                                self.reader_state = ReaderState.UNKNOWN_TAG
                                self.active_tag = None
                                self.active_item = None
                        elif response["command_code"] == "FE":
                            # FIXME: error case, detected once, should not happen
                            self.reader_state = ReaderState.READER_ERROR
                            self.active_tag = None
                            self.active_item = None
                        else:
                            self.active_address = None
                            self.active_tag = None
                            self.last_printed_tag = None
                            self.active_item = None
                            self.reader_state = ReaderState.READER_ERROR
                    except Exception:
                        self.reader_state = ReaderState.READER_CONNECTED
                        self.active_address = None
                        self.active_tag = None
                        self.last_printed_tag = None
                        self.active_item = None

                case ReaderState.PRINT_TAG:
                    if (
                        self.active_tag != self.last_printed_tag
                        and self.overall_state == OverallState.READY_TO_USE
                        and self.active_item is not None
                    ):
                        # Print different size signum sticker for CDs
                        if self.active_item.get("material_code") == "3":
                            signum_height = 40
                            minimum_font_height = 32
                        else:
                            signum_height = 42
                            minimum_font_height = 32
                        image = create_signum(
                            classification=self.active_item["classification"],
                            shelfmark=self.active_item["shelfmark"],
                            font_path="assets/arial.ttf",
                            minimum_font_height=minimum_font_height,
                            width=413,
                            height=signum_height,
                        )
                        qlr = BrotherQLRaster(self.printer.get("model", "QL-810W"))
                        qlr.exception_on_warning = False
                        instructions = convert(
                            qlr=qlr,
                            images=[image],
                            label="38",
                            rotate="auto",
                            threshold=70.0,
                            dither=False,
                            compress=True,
                            red=False,
                            dpi_600=False,
                            hq=False,
                        )
                        # Uncomment the line below to show the signum in a window for debugging purposes
                        # image.show()
                        send(
                            instructions=instructions,
                            printer_identifier=self.printer["identifier"],
                            backend_identifier=self.printer.get("backend", "pyusb"),
                            blocking=False,
                        )
                    else:
                        # If the tag is the same as the last printed one, do not print it again
                        pass

                    self.last_printed_tag = self.active_tag
                    self.reader_state = ReaderState.SINGLE_TAG_READ

        except KeyboardInterrupt:
            # KeyboardInterrupts are ignored
            pass

        except serial.SerialException:
            # Occurs when someone unplugs the reader. When it happens, reset the reader state and continue.
            self.serial_port.close()
            self.serial_port = None
            self.reader_state = ReaderState.NO_READER_CONNECTED
            self.last_printed_tag = None
            self.active_address = None
            self.active_tag = None
            self.reader_version = None
            pass

        except Exception as e:
            # FIXME: These exceptions are always sent to Sentry
            print(f"Error: {e}")
            print(traceback.format_exc())
            pass

        # Determine overall state based on battery, backend, registration, reader, and printer states
        if battery.percent < 10:
            self.overall_state = OverallState.BATTERY_LOW
        elif (
            (self.backend_state == BackendState.BACKEND_OK)
            and (self.registration_state == RegistrationState.REGISTRATION_SUCCEEDED)
            and (self.reader_state != ReaderState.NO_READER_CONNECTED)
            and (self.reader_state != ReaderState.READER_ERROR)
            and (self.reader_state != ReaderState.MULTIPLE_TAGS_DETECTED)
            and (self.reader_state != ReaderState.UNKNOWN_TAG)
            and (previousReaderState != ReaderState.READER_ERROR)
            and (previousReaderState != ReaderState.MULTIPLE_TAGS_DETECTED)
            and (previousReaderState != ReaderState.UNKNOWN_TAG)
            and (self.printer_state == PrinterState.PRINTER_CONNECTED)
        ):
            self.overall_state = OverallState.READY_TO_USE
        elif (
            (self.backend_state == BackendState.BACKEND_OK)
            and (self.registration_state == RegistrationState.REGISTRATION_SUCCEEDED)
            and (
                self.reader_state == ReaderState.READER_ERROR
                or previousReaderState == ReaderState.READER_ERROR
                or self.reader_state == ReaderState.MULTIPLE_TAGS_DETECTED
                or previousReaderState == ReaderState.MULTIPLE_TAGS_DETECTED
                or self.reader_state == ReaderState.UNKNOWN_TAG
                or previousReaderState == ReaderState.UNKNOWN_TAG
            )
            and (self.printer_state == PrinterState.PRINTER_CONNECTED)
        ):
            self.overall_state = OverallState.READY_WITH_ERROR
        elif self.backend_state == BackendState.BACKEND_ERROR_RESPONSE:
            self.overall_state = OverallState.READY_WITH_ERROR
        else:
            self.overall_state = OverallState.NOT_READY_TO_USE

        # Emit print station registration name
        self.print_station_registration_name_sig.emit(f"{self.print_station_registration_name}")

        # Emit state signals to update the UI
        self.backend_state_sig.emit(f"{self.backend_state.name}")
        self.registration_state_sig.emit(f"{self.registration_state.name}")
        self.reader_state_sig.emit(f"{self.reader_state.name}")
        self.printer_state_sig.emit(f"{self.printer_state.name}")
        self.overall_state_sig.emit(f"{self.overall_state.name}")

        # Emit status messages
        if self.backend_state == BackendState.BACKEND_OK:
            self.backend_statustext_sig.emit("Taustajärjestelmäversio 1.0.0")
        elif self.backend_state == BackendState.NO_BACKEND_RESPONSE:
            self.backend_statustext_sig.emit("Ei yhteyttä")
        else:
            self.backend_statustext_sig.emit("Virhetilanne.")

        if self.registration_state == RegistrationState.REGISTRATION_SUCCEEDED:
            self.registration_statustext_sig.emit(
                f"{self.internal_hostname} [{self.internal_ip_address}], OK"
            )
        else:
            self.registration_statustext_sig.emit(
                f"{self.internal_hostname} [{self.internal_ip_address}], EI OK"
            )

        self.reader_statustext_sig.emit(f"RFID-lukija, {self.reader_version}")

        if self.printer_state == PrinterState.PRINTER_CONNECTED:
            self.printer_statustext_sig.emit(f"{self.printer['identifier']}")
        else:
            self.printer_statustext_sig.emit("Tulostinta ei löydy")

        # Determine the main message to display on the UI. We try to formulate a message using natural language.
        if self.overall_state == OverallState.BATTERY_LOW:
            self.message_sig.emit(
                (
                    "<p><b>Virta vähissä!</b></p>"
                    "<p>Tietokoneen akku on miltei tyhjä. Tulostus on varmuuden vuoksi kytketty pois päältä.</p>"
                    "<p><b>Ohjeet:</b></p>"
                    "<p><ul><li>Käy viemässä tietokone lataukseen.</li></ul></p>"
                )
            )
        elif self.overall_state == OverallState.NOT_READY_TO_USE:
            positives, negatives, fixes = [], [], []
            if self.backend_state == BackendState.BACKEND_OK:
                positives.append("taustajärjestelmä toimii")
            if self.registration_state == RegistrationState.REGISTRATION_SUCCEEDED:
                positives.append("asema on valtuutettu")
            if self.reader_state is not ReaderState.NO_READER_CONNECTED:
                positives.append("RFID-lukija on yhdistetty")
            if self.printer_state == PrinterState.PRINTER_CONNECTED:
                positives.append("tulostin löytyy")
            if self.backend_state == BackendState.NO_BACKEND_RESPONSE:
                negatives.append("taustajärjestelmä ei vastaa")
                fixes.append("<li>Varmista, että toimipaikan verkkoyhteys toimii</li>")
            elif self.backend_state == BackendState.BACKEND_ERROR_RESPONSE:
                negatives.append("taustajärjestelmässä on virhe")
                fixes.append(
                    "<li>Pyydä toimipaikan pääkäyttäjää ilmoittamaan taustajärjestelmän virheestä</li>"
                )
            if self.registration_state == RegistrationState.REGISTRATION_FAILED:
                negatives.append("tulostusasemalle ei saatu valtuuksia")
                if self.backend_state is not BackendState.NO_BACKEND_RESPONSE:
                    fixes.append(
                        "<li>Pyydä toimipaikan pääkäyttäjää pyytämään tarroitusasemalle valtuudet</li>"
                    )
            if self.reader_state == ReaderState.NO_READER_CONNECTED:
                negatives.append("RFID-lukijaa ei ole yhdistetty")
                fixes.append(
                    "<li>Varmista, että RFID-lukija on yhdistetty USB-porttiin. Odota kytkemisen jälkeen hetki.</li>"
                )
            if self.printer_state == PrinterState.NO_PRINTER_CONNECTED:
                negatives.append("tulostinta ei löydy")
                fixes.append(
                    "<li>Varmista, että tulostin on yhdistetty USB-porttiin ja päällä</li>"
                )
            conjunction = ""
            if len(positives) > 0 and len(negatives) > 0:
                conjunction = ", mutta "
            self.message_sig.emit(
                (
                    "<p><b>Tarroja ei voi tulostaa juuri nyt.</b></p>"
                    "<p>"
                    f"{join_with_and(positives, "ja").capitalize()}{conjunction}{join_with_and(negatives, "eikä")}."
                    "</p>"
                    "<p><b>Ohjeet:</b>"
                    f"<ul>{"\n".join(fixes)}</ul>"
                    "</p>"
                )
                if len(fixes) > 0
                else ""
            )
        elif self.overall_state == OverallState.READY_WITH_ERROR:
            if self.reader_state == ReaderState.MULTIPLE_TAGS_DETECTED:
                self.message_sig.emit(
                    (
                        "<p><b>Virhetilanne</b></p>"
                        "<p>Lukija havaitsee useita niteitä.</p>"
                        "<p><b>Ohjeet:</b></p>"
                        "<ul>"
                        "<li>Varmista, että lukijan läheisyydessä ei ole muita niteitä kuin se, "
                        "jota yrität tarroittaa</li>"
                        "</ul>"
                    )
                )
            elif (
                self.reader_state == ReaderState.UNKNOWN_TAG
                or previousReaderState == ReaderState.UNKNOWN_TAG
            ):
                self.message_sig.emit(
                    (
                        "<p><b>Virhetilanne</b></p>"
                        "<p>Niteessä on viallinen RFID-tagi."
                        "Se pitää vaihtaa tai aktivoida ennen signum-tarran tulostamista.</p>"
                        "<p><b>Ohjeet:</b></p>"
                        "<ul>"
                        "<li>Laita nide syrjään. Anna vuoron lopuksi kaikki vastaavat niteet kirjastovirkailijalle. "
                        "Kirjastovirkailija lähettää niteen jatkokäsittelyyn.</li>"
                        "</ul>"
                    )
                )
            elif self.backend_state == BackendState.BACKEND_ERROR_RESPONSE:
                self.message_sig.emit(
                    "<p><b>Virhetilanne</b></p>"
                    "<p>Niteen tietoja ei saada haettua taustajärjestelmästä taustajärjestelmän palauttaman virheen vuoksi.</p>"
                    "<p><b>Ohjeet:</b></p>"
                    "<ul>"
                    "<li>Odota vähän aikaa ja kokeile samalla tai eri niteellä uudestaan.</li>"
                    "</ul>"
                )
            elif self.backend_state == BackendState.BACKEND_EMPTY_RESPONSE:
                self.message_sig.emit(
                    "<p><b>Virhetilanne</b></p>"
                    "<p>Niteelle ei ole saatavilla tietoja taustajärjestelmässä.</p>"
                    "<p><b>Ohjeet:</b></p>"
                    "<ul>"
                    "<li>Ilmoita tilanteesta kirjastovirkailijalle.</li>"
                    "</ul>"
                )
            else:
                self.message_sig.emit(
                    (
                        "<p><b>Virhetilanne</b></p>"
                        "<p>Lukija palauttaa virheellisiä lukutuloksia.</p>"
                        "<p><b>Ohjeet:</b></p>"
                        "<ul>"
                        "<li>Varmista, ettei lukijan läheisyydessä ole radiohäiriötä aiheuttavaa esinettä tai laitetta,"
                        " esimerkiksi toista RFID-lukijaa.</li>"
                        "<li>Varmista, ettei lukijan läheisyydessä ole muita niteitä kuin se, "
                        "jota yrität tarroittaa</li>"
                        "<li>CD, DVD ja Blu-Ray -levyt saattavat myös aiheuttaa häiriöitä. Kokeile kääntää kotelo "
                        "ympäri tai liikuttaa sitä hitaasti lukijan päällä.</li>"
                        "</ul>"
                    )
                )
        elif (
            self.reader_state == ReaderState.SINGLE_TAG_READ
            or self.reader_state == ReaderState.PRINT_TAG
        ) and self.active_tag is not None:
            # FIXME: Replace with the book title
            self.message_sig.emit(f"{self.item_data_message}")
        else:
            self.message_sig.emit(
                (
                    "<p><b>Valmiina tulostamaan tarroja!</b></p>"
                    "<p><b>Ohjeet:</b>"
                    "<ol>"
                    "<li>Aseta nide lukutason päälle</li>"
                    "<li>Tulostin tulostaa tarran luettuaan niteen RFID-tunnisteen</li>"
                    "<li>Kiinnitä tarra niteeseen</li>"
                    "</ol>"
                )
            )


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
