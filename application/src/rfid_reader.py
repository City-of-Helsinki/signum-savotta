"""
RFID reader module for Signum labeller application
Contains RFID-specific classes, constants, and utility functions
"""

import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional

import sentry_sdk
import serial
from helmet_rfid_tag import HelmetRfidTag


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


class ReaderState(Enum):
    """
    RFID reader states.
    """

    NO_READER_CONNECTED = 0
    READER_CONNECTED = 1
    SINGLE_TAG_DETECTED = 2
    MULTIPLE_TAGS_DETECTED = 3
    SINGLE_TAG_READ = 4
    TAG_PARSED = 5
    READER_ERROR = 6
    UNKNOWN_TAG = 7


# FIXME: The response parsing should be dynamic rather than comparing to static responses.
RESPONSE_EMPTY = None
RESPONSE_READER_READY_1 = bytes.fromhex("d500090400110a05021b972a")
RESPONSE_READER_READY_2 = bytes.fromhex("d500090400110a050119e23b")
RESPONSE_NO_TAG_DETECTED = bytes.fromhex("d60007fe00000700af19")
RESPONSE_SINGLE_TAG_DETECTED = bytes.fromhex("d60007fe0000000126af")


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
    except Exception as e:
        sentry_sdk.capture_exception(error=e)
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
    except Exception as e:
        sentry_sdk.capture_exception(error=e)
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
    except Exception as e:
        sentry_sdk.capture_exception(error=e)
        return None


@dataclass
class RFIDResult:
    """
    Result structure for RFID reader operations
    """

    state: ReaderState
    tag: Optional[HelmetRfidTag] = None
    address: Optional[str] = None
    version: Optional[str] = None
    error: Optional[str] = None


class RFIDReader:
    """
    RFID reader class that handles all RFID-specific operations and state management
    """

    def __init__(self):
        self.state: ReaderState = ReaderState.NO_READER_CONNECTED
        self.serial_port: serial.Serial | None = None
        self.serial_port_number: int = 1
        self.active_address: str | None = None
        self.active_tag: HelmetRfidTag | None = None
        self.reader_version: str | None = None
        self.reader_wait: float = 0.1

    def send_data(self, data: bytes):
        """
        send_data sends data to the autoconfigured serial port

        :parameter data: bytes the data to send
        """
        if self.serial_port:
            self.serial_port.write(data)

    def read_data(self) -> bytes | None:
        """
        read_data reads data from the autoconfigured serial port

        :return: bytes the read data
        """
        if self.serial_port and self.serial_port.in_waiting > 0:
            data = self.serial_port.read_all()
            return data
        return None

    def update(self) -> RFIDResult:
        """
        Updates the RFID reader state machine and returns current status

        :return: RFIDResult with current state and data
        """
        try:
            match self.state:
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
                            if ver:
                                self.reader_version = (
                                    f"{ver['vendor']} {ver['major_value']}."
                                    f"{ver['minor_value']}.{ver['build_version']}"
                                )
                            self.state = ReaderState.READER_CONNECTED
                        else:
                            if response is not None:
                                # This branch will handle cases where the reader is responding with READ_BLOCK_UID
                                # and the response from the reader takes longer than the configured wait time
                                self.state = ReaderState.READER_CONNECTED
                            else:
                                self.state = ReaderState.NO_READER_CONNECTED

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
                                self.state = ReaderState.SINGLE_TAG_READ
                            elif uid_res["num_tags"] > 1:
                                self.active_address = None
                                self.active_tag = None
                                self.state = ReaderState.MULTIPLE_TAGS_DETECTED
                            else:
                                self.active_address = None
                                self.active_tag = None
                                self.state = ReaderState.READER_CONNECTED
                        else:
                            # The reader responds slowly
                            # This means that the response to the command is available at next loop iteration
                            # We handle this case simply by dropping to READER_CONNECTED
                            self.active_address = None
                            self.active_tag = None
                            self.state = ReaderState.READER_CONNECTED
                    else:
                        self.active_address = None
                        self.active_tag = None
                        self.state = ReaderState.NO_READER_CONNECTED

                case ReaderState.SINGLE_TAG_READ:
                    cmd = build_command_hex(
                        Command.ADDR_READ_MULTIBLOCK.value, f"{self.active_address}00080c"
                    )
                    self.send_data(bytes.fromhex(cmd))
                    time.sleep(self.reader_wait)
                    resp = self.read_data()
                    try:
                        response = parseReadMultiblockResponse(resp)
                        if response and response["checksum_match"]:
                            helmet_rfid_tag = HelmetRfidTag(response["raw_blocks"])
                            if helmet_rfid_tag.welformed_data:
                                self.active_tag = helmet_rfid_tag
                                self.state = ReaderState.TAG_PARSED
                            else:
                                self.state = ReaderState.UNKNOWN_TAG
                                self.active_tag = None
                        elif response and response["command_code"] == "FE":
                            # FIXME: error case, detected once, should not happen
                            self.state = ReaderState.READER_ERROR
                            self.active_tag = None
                        else:
                            self.active_address = None
                            self.active_tag = None
                            self.state = ReaderState.READER_ERROR
                    except Exception:
                        self.state = ReaderState.READER_CONNECTED
                        self.active_address = None
                        self.active_tag = None

                case ReaderState.TAG_PARSED:
                    # Print processing is handled by the Backend class
                    # After printing, continue monitoring
                    self.state = ReaderState.SINGLE_TAG_READ

        except serial.SerialException as e:
            # Occurs when someone unplugs the reader. When it happens, reset the reader state and continue.
            sentry_sdk.capture_exception(error=e)
            if self.serial_port:
                self.serial_port.close()
            self.serial_port = None
            self.state = ReaderState.NO_READER_CONNECTED
            self.active_address = None
            self.active_tag = None
            self.reader_version = None

        except Exception as e:
            # Don't change state on unexpected errors to prevent cascading failures
            sentry_sdk.capture_exception(error=e)

        return RFIDResult(
            state=self.state,
            tag=self.active_tag,
            address=self.active_address,
            version=self.reader_version,
        )
