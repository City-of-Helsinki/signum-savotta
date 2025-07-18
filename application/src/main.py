import serial
from enum import Enum
import time

import sys

from PySide6.QtGui import QGuiApplication, QIcon, QPixmap
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtCore import QObject, QTimer, Signal

from brother_ql.raster import BrotherQLRaster
from brother_ql.conversion import convert
from brother_ql.backends.helpers import discover, send
from PIL import Image, ImageDraw, ImageFont

from helmet_rfid_tag import HelmetRfidTag

# Import resources from Qt Resource Compiler
# Compile assets with command pyside6-rcc assets.qrc -o src/assets_rc.py
import assets_rc

import traceback

import psutil

# Import ctypes to set Windows application icon in taskbar
import ctypes
myappid = 'helsinki.signumsavotta.application.1' # arbitrary string
ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)


class Command(Enum):
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
    :return: ImageFont font The font which will fit, tuple[float, float, float, float] bbox The bounding box, height float the height of the text in pixels
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


def create_signum(classification, paasana, font_path, minimum_font_height, width, height):
    """
    get_font_size_for_text Creates a signum image for printing

    :param classification: the classification (in YKL)
    :param paasana: three letter word for alphabetical sorting
    :param font_path: path to the font to use
    :param minimum_font_height: minimum font size to use (text will use all the space it can get)
    :param width: width of the signum in pixels. Note that this has to correspond to brother-ql continous roll widths 
    :param width: height of the signum in pixels. The minimum value is 42 which corresponds to 9mm. Values less than that are considered to be CD case signums which will result in additional blank space added.
    :return: Image the signum image
    """

    # Standard label height is 42 pixels (9 mm) which is also the minumum height for brother-ql cutting unit.
    # Signums labels with maximum label text of 6mm height are used in CD jewel cases and digipacks.
    # CD signum labels are printed with extra blank space above and below the signum.
    # The label is wrapped around the case. This ensures that the label adhesive works properly.
    im_height = height
    if height < 42:
        im_height = height * 5

    image = Image.new('RGB', (width, im_height), color='white')
    draw = ImageDraw.Draw(image)

    luokitus_font, luokitus_bbox, luokitus_height = get_font_size_for_text(classification, minimum_font_height, font_path, height)
    paasana_font, paasana_bbox, paasana_height = get_font_size_for_text(paasana, minimum_font_height, font_path, height)

    paasana_position = (width - draw.textlength(paasana, font=paasana_font), (im_height - paasana_height) / 2 - paasana_bbox[1])
    luokitus_position = (0, (im_height - luokitus_height) / 2 - luokitus_bbox[1])

    draw.text(luokitus_position, classification, fill='black', font=luokitus_font)
    draw.text(paasana_position, paasana, fill='black', font=paasana_font)
    
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

    :param data: bytearray the data for which the checksum is to be calculated for
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

#FIXME: Implement checksum error checking
def parseReadVersionResponse(data):
    try:
        return {
            "vendor": "3M" if data[6] == 5 else "Unknown",
            "major_value": data[7],
            "minor_value": data[8],
            "build_version": data[9]
        }
    except:
        return None

#FIXME: Implement checksum error checking
def parseReadBlockUIDResponse(data):
    try:
        num_tags = data[7]
        tags = []
        for i in range(num_tags):
            tags.append({
                "dsfid": data[8 + i*8],
                "address": data[9 + i*8: 17 + i*8]
            })
            
        return {
            "errorcode": data[4],
            "afi": data[5],
            "response_options": data[6],
            "num_tags": num_tags,
            "tags": tags
        }
    except:
        return None

def parseReadMultiblockResponse(data):
    try:
        data_blocks =  bytes(data[15:47])
        resp = {
            "command_code": f'{data[3]:02X}',
            "error_code":  f'{data[4]:02X}',
            "address":  data[5:13].hex(),
            "start_block":  f'{data[13]:02X}',
            "block_count":  f'{data[14]:02X}',
            "raw_blocks":  data[15:47],
            "checksum_match": False
        }
        if bytes.fromhex(build_command_hex(
            Command.ADDR_READ_MULTIBLOCK.value,
            f"{resp['error_code']}{resp['address']}{resp['start_block']}{resp['block_count']}{data_blocks.hex()}"
        )).hex() == data.hex():
            resp["checksum_match"] = True
        return resp
    except:
        return None

# This function is simply for making the tone of voice of error messages a bit more humane.
def join_with_and(items, last_separator="ja"):
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
    NOT_READY_TO_USE = 0
    READY_TO_USE = 1
    READY_WITH_ERROR = 2
    BATTERY_LOW = 3

class BackendState(Enum):
    NO_BACKEND_RESPONSE = 0
    BACKEND_OK = 1
    BACKEND_ERROR = 2

class RegistrationState(Enum):
    REGISTRATION_FAILED = 0
    REGISTRATION_SUCCEEDED = 1

class ReaderState(Enum):
    NO_READER_CONNECTED = 0
    READER_CONNECTED = 1
    SINGLE_TAG_DETECTED = 2
    MULTIPLE_TAGS_DETECTED = 3
    SINGLE_TAG_READ = 4
    PRINT_TAG = 5
    READER_ERROR = 6
    UNKNOWN_TAG = 7

class PrinterState(Enum):
    NO_PRINTER_CONNECTED = 0
    PRINTER_CONNECTED = 1

RESPONSE_EMPTY = None
RESPONSE_READER_READY_1 = bytes.fromhex("d500090400110a05021b972a")
RESPONSE_READER_READY_2 = bytes.fromhex("d500090400110a050119e23b")
RESPONSE_NO_TAG_DETECTED = bytes.fromhex("d60007fe00000700af19")
RESPONSE_SINGLE_TAG_DETECTED = bytes.fromhex("d60007fe0000000126af")

# FIXME: Remove from final. Only for testing low battery state.
class DummyBattery:
    percent = 0
    power_plugged = False
    def __init__(self, percent, power_plugged):
        self.percent = percent
        self.power_plugged = power_plugged

class Backend(QObject):

    # FIXME: Load these from configuration file
    print_station_registration_name = "PASILA 01"
    print_station_registration_key = ""

    # Signals for updating the UI
    print_station_registration_name_sig = Signal(str, arguments=['string'])
    backend_state_sig = Signal(str, arguments=['string'])
    registration_state_sig = Signal(str, arguments=['string'])
    reader_state_sig = Signal(str, arguments=['string'])
    printer_state_sig = Signal(str, arguments=['string'])
    overall_state_sig = Signal(str, arguments=['string'])
    message_sig = Signal(str, arguments=['string'])
    backend_statustext_sig = Signal(str, arguments=['string'])
    registration_statustext_sig = Signal(str, arguments=['string'])
    reader_statustext_sig = Signal(str, arguments=['string'])
    printer_statustext_sig = Signal(str, arguments=['string'])
    iteration_sig = Signal(int, arguments=['int'])
    batterypercentage_sig = Signal(int, arguments=['int'])
    batterycharging_sig = Signal(bool, arguments=['bool'])

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
    last_printed_tag = None
    serial_port_number = 1
    serial_port = None

    # Printer initial state variables
    printer_state = PrinterState.NO_PRINTER_CONNECTED
    printer = None
    printer_identifier = None

    # UI error messaging grace period in event loop cycles
    error_cycles = 0
    error_cycles_grace_period = 3

    # Timing values FIXME: Load from configuration file
    ui_interval = 200
    reader_wait = 0.1
    iteration = 0
    read_message = ""

    def __init__(self):
        super().__init__()
        self.timer = QTimer()
        self.timer.setInterval(self.ui_interval)
        self.timer.timeout.connect(self.reader_loop)
        self.timer.start()

    def send_data(self, data):
        self.serial_port.write(data)

    def read_data(self):
        if self.serial_port.in_waiting > 0:
            data = self.serial_port.read_all()
            return data
        return None

    # FIXME: The reader event loop contains also the UI event loop. Should this code ever be reused, the two need to be separate.
    def reader_loop(self):

        # Store the previous reader state for use in determining the overall status.
        # Solution for preventing read error scenarios from causing flickering in the UI
        previousReaderState = self.reader_state

        # Emit just to inform that the reader loop is on
        if self.iteration < 10:
            self.iteration = self.iteration + 1
        else:
            self.iteration = 1
        self.iteration_sig.emit(self.iteration)

        # Laptop battery
        battery = psutil.sensors_battery()
        if battery:
            self.batterycharging_sig.emit(battery.power_plugged)
            self.batterypercentage_sig.emit(battery.percent)

        # Autoconfigure printer
        devices = discover(backend_identifier='pyusb')
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
                                port=f"COM{self.serial_port_number}",
                                baudrate=19200,
                                timeout=1
                            )
                        except serial.SerialException as e:
                            if self.serial_port is not None:
                                self.serial_port.close()
                            self.serial_port = None
                            if self.serial_port_number < 10:
                                self.serial_port_number += 1
                            else:
                                self.serial_port_number = 1
                    else:
                        # Initialize the reader. For some reason, this command needs to be read from the serial interface immediately.
                        # Any delay between send and read will cause errors.
                        self.send_data(bytes.fromhex('D5 00 05 04 00 11 8C 66'))
                        response = self.read_data()
                        if response == RESPONSE_READER_READY_1 or response == RESPONSE_READER_READY_2:
                            # 3M Documentation does not say anything about this command
                            # Found via reverse engineering
                            self.send_data(bytes.fromhex('d60010130601000200030004000b000a00fdbf'))
                            time.sleep(self.reader_wait)
                            self.read_data()
                            # Get reader version
                            self.send_data(bytes.fromhex(build_command_hex(Command.NORM_READER_VERSION.value,"")))
                            time.sleep(self.reader_wait)
                            ver = parseReadVersionResponse(self.read_data())
                            self.reader_version = f"{ver['vendor']} {ver['major_value']}.{ver['minor_value']}.{ver['build_version']}"
                            self.reader_state = ReaderState.READER_CONNECTED
                        else:
                            if response is not None:
                                # This branch will handle cases where the reader is responding with READ_BLOCK_UID
                                # and the response from the reader takes longer than the configured wait time
                                self.reader_state = ReaderState.READER_CONNECTED
                            else:
                                self.reader_state = ReaderState.NO_READER_CONNECTED

                case ReaderState.READER_CONNECTED | ReaderState.MULTIPLE_TAGS_DETECTED | ReaderState.READER_ERROR | ReaderState.UNKNOWN_TAG:
                    cmd = build_command_hex(Command.NORM_READ_BLOCK_UID.value, "0007")
                    self.send_data(bytes.fromhex(cmd))
                    time.sleep(self.reader_wait)
                    response = self.read_data()
                    if response != RESPONSE_EMPTY:
                        # FIXME: implement logic to handle checksum errors once that's implemented
                        uid_res = parseReadBlockUIDResponse(response)
                        if uid_res is not None:
                            if(uid_res["num_tags"] == 1 and uid_res["afi"] == 0):
                                self.active_address = uid_res["tags"][0]["address"].hex()
                                self.last_printed_tag = None
                                self.reader_state = ReaderState.SINGLE_TAG_READ
                            elif(uid_res["num_tags"] > 1):
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
                            # The reader responds slowly which means that the response to the command is available at next loop iteration
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
                        Command.ADDR_READ_MULTIBLOCK.value,
                        f"{self.active_address}00080c"
                    )
                    self.send_data(bytes.fromhex(cmd))
                    time.sleep(self.reader_wait)
                    resp = self.read_data()
                    try:
                        response = parseReadMultiblockResponse(resp)
                        if response["checksum_match"]:
                            helmet_rfid_tag = HelmetRfidTag(response["raw_blocks"])
                            if(helmet_rfid_tag.welformed_data):
                                msg = []
                                msg.append("<p><ul>")
                                d = helmet_rfid_tag.__dict__
                                for field in d:
                                    msg.append(f"<li>{field}: {d[field]}</li>")
                                msg.append("</ul></p>")
                                self.read_message = "".join(msg)                                
                                self.active_tag = helmet_rfid_tag
                                self.reader_state = ReaderState.PRINT_TAG
                            else:
                                self.reader_state = ReaderState.UNKNOWN_TAG
                        elif response["command_code"] == "FE":
                            # FIXME: error case, detected once, should not happen
                            self.reader_state = ReaderState.READER_ERROR
                        else:
                            self.active_address = None
                            self.active_tag = None
                            self.last_printed_tag = None
                            self.reader_state = ReaderState.READER_ERROR
                    except:
                        self.reader_state = ReaderState.READER_CONNECTED

                case ReaderState.PRINT_TAG:
                    if (self.active_tag != self.last_printed_tag) and (self.overall_state == OverallState.READY_TO_USE):
                        # FIXME: Replace with values fetched from the backend
                        image = create_signum(classification="78.12345", paasana="KLA", font_path='assets/arial.ttf', minimum_font_height=32, width=413, height=40)
                        qlr = BrotherQLRaster(self.printer.get('model', 'QL-810W'))
                        qlr.exception_on_warning = False
                        instructions = convert(
                            qlr=qlr,
                            images=[image],
                            label='38',
                            rotate='auto',
                            threshold=70.0,
                            dither=False,
                            compress=True,
                            red=False,
                            dpi_600=False,
                            hq=False
                        )
                        # Uncomment the line below to show the signum in a window for debugging purposes
                        # image.show()
                        send(
                            instructions=instructions,
                            printer_identifier=self.printer['identifier'],
                            backend_identifier=self.printer.get('backend', 'pyusb'),
                            blocking=False
                        )
                    else:
                        # If the tag is the same as the last printed one, do not print it again
                        pass
                    
                    self.last_printed_tag = self.active_tag
                    self.reader_state = ReaderState.SINGLE_TAG_READ

        except KeyboardInterrupt:
            # KeyboardInterrupts are ignored
            pass

        except serial.SerialException as e:
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
        if(battery.percent < 10):
            self.overall_state = OverallState.BATTERY_LOW
        elif (
            (self.backend_state == BackendState.BACKEND_OK) and
            (self.registration_state == RegistrationState.REGISTRATION_SUCCEEDED) and
            (self.reader_state != ReaderState.NO_READER_CONNECTED) and
            (self.reader_state != ReaderState.READER_ERROR) and
            (self.reader_state != ReaderState.MULTIPLE_TAGS_DETECTED) and
            (self.reader_state != ReaderState.UNKNOWN_TAG) and
            (previousReaderState != ReaderState.READER_ERROR) and 
            (previousReaderState != ReaderState.MULTIPLE_TAGS_DETECTED) and
            (previousReaderState != ReaderState.UNKNOWN_TAG) and
            (self.printer_state == PrinterState.PRINTER_CONNECTED)
            ):
            self.error_cycles = 0
            self.overall_state = OverallState.READY_TO_USE
        elif (
            (self.backend_state == BackendState.BACKEND_OK) and
            (self.registration_state == RegistrationState.REGISTRATION_SUCCEEDED) and
            (self.reader_state == ReaderState.READER_ERROR or
             previousReaderState == ReaderState.READER_ERROR or
             self.reader_state == ReaderState.MULTIPLE_TAGS_DETECTED or
             previousReaderState == ReaderState.MULTIPLE_TAGS_DETECTED or
             self.reader_state == ReaderState.UNKNOWN_TAG or
             previousReaderState == ReaderState.UNKNOWN_TAG
            ) and
            (self.printer_state == PrinterState.PRINTER_CONNECTED)
            ):
            self.error_cycles = 0
            self.overall_state = OverallState.READY_WITH_ERROR
        else:
            # Allow grace period when transitioning to NOT_READY_TO_USE state to avoid flickering in the UI for brief loss of connectivity
            # FIXME: Use transition states instead and have specific grace periods for each of them
            if (self.overall_state == OverallState.READY_TO_USE) and (self.error_cycles < self.error_cycles_grace_period):
                self.error_cycles += 1
                OverallState.READY_TO_USE
            else:
                self.error_cycles = 0
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
            self.backend_statustext_sig.emit("Ei yhteyttä taustajärjestelmään")
        else:
            self.backend_statustext_sig.emit("Taustajärjestelmävirhe: Ei yhteyttä Sierraan")
        
        if self.registration_state == RegistrationState.REGISTRATION_SUCCEEDED:
            self.registration_statustext_sig.emit(f"{self.print_station_registration_name}, valtuutus ok")
        else:
            self.registration_statustext_sig.emit(f"{self.print_station_registration_name}, ei valtuutusta")

        self.reader_statustext_sig.emit(f"RFID-lukija, {self.reader_version}")

        if self.printer_state == PrinterState.PRINTER_CONNECTED:
            self.printer_statustext_sig.emit(f"{self.printer['identifier']}")
        else:
            self.printer_statustext_sig.emit("Tulostinta ei löydy")

        # Determine the main message to display on the UI. We try to formulate a message using natural language.
        if self.overall_state == OverallState.BATTERY_LOW:
            self.message_sig.emit(
                "<p><b>Virta vähissä!</b></p>" +
                "<p>Tietokoneen akku on miltei tyhjä. Tulostus on varmuuden vuoksi kytketty pois päältä.</p>"
                "<p><b>Ohjeet:</b></p>" +
                "<p><ul><li>Käy viemässä tietokone lataukseen.</li></ul></p>"

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
            elif self.backend_state == BackendState.BACKEND_ERROR:
                negatives.append("taustajärjestelmässä on virhe")
                fixes.append("<li>Pyydä toimipaikan pääkäyttäjää ilmoittamaan taustajärjestelmän virheestä</li>")
            if self.registration_state == RegistrationState.REGISTRATION_FAILED:
                negatives.append("tulostusasemalle ei saatu valtuuksia")
                if self.backend_state is not BackendState.NO_BACKEND_RESPONSE:
                    fixes.append("<li>Pyydä toimipaikan pääkäyttäjää pyytämään tarroitusasemalle valtuudet</li>")
            if self.reader_state == ReaderState.NO_READER_CONNECTED:
                negatives.append("RFID-lukijaa ei ole yhdistetty")
                fixes.append("<li>Varmista, että RFID-lukija on yhdistetty USB-porttiin. Odota kytkemisen jälkeen hetki.</li>")
            if self.printer_state == PrinterState.NO_PRINTER_CONNECTED:
                negatives.append("tulostinta ei löydy")
                fixes.append("<li>Varmista, että tulostin on yhdistetty USB-porttiin ja päällä</li>")
            conjunction = ""
            if len(positives) > 0 and len(negatives) > 0:
                conjunction = ", mutta "
            self.message_sig.emit(
                "<p><b>Tarroja ei voi tulostaa juuri nyt.</b></p>" +
                f"<p>{join_with_and(positives, "ja").capitalize()}{conjunction}{join_with_and(negatives, "eikä")}.</p>" +
                f"<p><b>Ohjeet:</b><ul>{"\n".join(fixes)}</ul></p>" if len(fixes) > 0 else ""
            )
        elif self.overall_state == OverallState.READY_WITH_ERROR:
            if(self.reader_state == ReaderState.MULTIPLE_TAGS_DETECTED):
                self.message_sig.emit(
                    "<p><b>Virhetilanne</b></p>" +
                    "<p>Lukija havaitsee useita niteitä.</p>"
                    "<p><b>Ohjeet:</b></p>" +
                    "<p><ul><li>Varmista, että lukijan läheisyydessä ei ole muita niteitä kuin se, jota yrität tarroittaa</li></ul></p>"
                )
            elif(self.reader_state == ReaderState.UNKNOWN_TAG or previousReaderState == ReaderState.UNKNOWN_TAG):
                self.message_sig.emit(
                    "<p><b>Virhetilanne</b></p>" +
                    "<p>Niteessä on viallinen RFID-tagi. Se pitää vaihtaa ennen signum-tarran tulostamista.</p>"
                    "<p><b>Ohjeet:</b></p>" +
                    "<p><ul><li>Laita nide syrjään. Anna vuoron lopuksi kaikki vastaavat niteet kirjastovirkailijalle. Kirjastovirkailija lähettää niteen jatkokäsittelyyn.</li></ul></p>"
                )
            else:
                self.message_sig.emit(
                    "<p><b>Virhetilanne</b></p>" +
                    "<p>Lukija palauttaa virheellisiä lukutuloksia.</p>"
                    "<p><b>Ohjeet:</b></p>" +
                    "<p><ul>" +
                    "<li>Varmista, ettei lukijan läheisyydessä ole radiohäiriötä aiheuttavaa esinettä tai laitetta, esimerkiksi toista RFID-lukijaa.</li>" +
                    "<li>Varmista, ettei lukijan läheisyydessä ole muita niteitä kuin se, jota yrität tarroittaa</li>" +
                    "<li>CD, DVD ja Blu-Ray -levyt saattavat myös aiheuttaa häiriöitä. Kokeile kääntää kotelo ympäri tai liikuttaa sitä hitaasti lukijan päällä.</li>" +
                    "</ul></p>"
                )
        elif (
            (self.reader_state == ReaderState.SINGLE_TAG_READ or self.reader_state == ReaderState.PRINT_TAG) and
            self.active_tag is not None
            ):
            # FIXME: Replace with the book title
            self.message_sig.emit(f"{self.read_message}")
        else:
            self.message_sig.emit(
                "<p><b>Valmiina tulostamaan tarroja!</b></p>" +
                "<p><b>Ohjeet:</b><ol><li>Aseta nide lukutason päälle</li><li>Tulostin tulostaa tarran luettuaan niteen RFID-tunnisteen</li><li>Kiinnitä tarra niteeseen</li></ol>"
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
engine.load(':/main.qml')
engine.rootObjects()[0].setProperty('backend', backend)

for object in engine.rootObjects():
    if object.isWindowType():
        object.setIcon(app_icon)
        object.setTitle("Signum-savotta")
        object.requestActivate()

sys.exit(app.exec())