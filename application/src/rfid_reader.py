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


class ResponseStyle(Enum):
    """
    Response style for Read Multiblock responses
    """

    OLD = "old"
    NEW_WITH_LOCK_INFORMATION = "NEW_WITH_LOCK_INFORMATION"
    NEW_WITHOUT_LOCK_INFORMATION = "NEW_WITHOUT_LOCK_INFORMATION"


# FIXME: The response parsing should be dynamic rather than comparing to static responses.
RESPONSE_EMPTY = None
RESPONSE_READER_READY_1 = bytes.fromhex("d500090400110a05021b972a")
RESPONSE_READER_READY_2 = bytes.fromhex("d500090400110a050119e23b")


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


@dataclass
class RFIDResponseValidation:
    """
    Result structure for RFID response validation
    """

    is_valid: bool
    command_code: Optional[int] = None
    error_code: Optional[int] = None
    payload_data: Optional[bytes] = None
    error_message: Optional[str] = None


# ============================================================================
# RFID Protocol Request and Response Dataclasses
# Based on 3M RFID Reader Protocol Specification v1.0.0
# ============================================================================


@dataclass
class TagData:
    """Tag data structure for Read Block UID responses"""

    dsfid: int  # 1 byte - Data Storage Format Identifier
    address: bytes  # 8 bytes - Tag serial number


@dataclass
class BlockData:
    """Block data structure for Read Multiblock responses"""

    block_number: int  # 1 byte - Block number (0-255)
    lock_status: int  # 1 byte - Lock/Error status
    data: bytes  # 4 bytes - Block data


# Read Block UID (0xFE) - Poll for tags
@dataclass
class ReadBlockUIDRequest:
    """Read Block UID command request"""

    afi: int = 0  # 1 byte - Application Family Identifier (0 for all tags)
    response_options: int = 0  # 1 byte - Response options bitfield
    protocols: Optional[int] = (
        None  # 1 byte - Protocol selection (when bit6 set in response_options)
    )


@dataclass
class ReadBlockUIDResponse:
    """Read Block UID command response"""

    error_code: int  # 1 byte - Error code
    afi: int  # 1 byte - Requested AFI
    response_options: int  # 1 byte - Response options
    num_tags: int  # 1 byte - Number of transponders found
    tags: list[TagData]  # Variable - Tag data for each found tag


# Reader Version (0x11) - Get firmware version
@dataclass
class ReaderVersionRequest:
    """Reader Version command request - no fields"""

    pass


@dataclass
class ReaderVersionResponse:
    """Reader Version command response"""

    error_code: int  # 1 byte - Error code
    vendor_id: int  # 1 byte - 0x0A for 3M readers
    major_value: int  # 1 byte - Major version
    minor_value: int  # 1 byte - Minor version
    build_version: int  # 1 byte - Build version


# ISO Pass thru (0x14) - Send raw ISO air commands
@dataclass
class ISOPassThruRequest:
    """ISO Pass thru command request"""

    send_data_size: int  # 2 bytes - Size of ISO air command send data
    receive_size: int  # 2 bytes - Size of air command response
    control_options: int  # 2 bytes - Control options bitfield
    rf_flags: Optional[int] = None  # 1 byte - RF flags (when bit15 set in control_options)
    send_data: bytes = bytes()  # Variable - ISO air command data


@dataclass
class ISOPassThruResponse:
    """ISO Pass thru command response"""

    error_code: int  # 1 byte - Error code
    result_flags: int  # 1 byte - Result flags for debugging
    receive_size: int  # 2 bytes - Size of air command response data
    receive_data: bytes  # Variable - ISO air command response data


# Quiet (0x01) - Quiet a specific tag
@dataclass
class QuietRequest:
    """Quiet command request"""

    address: bytes  # 8 bytes - Tag serial number


@dataclass
class QuietResponse:
    """Quiet command response"""

    error_code: int  # 1 byte - Error code
    address: bytes  # 8 bytes - Tag serial number


# Read Multiblock (0x02) - Read block(s) data from a specific tag
@dataclass
class ReadMultiblockRequest:
    """Read Multiblock command request"""

    address: bytes  # 8 bytes - Tag serial number
    first_block_number: int  # 1 byte - First block to read (0-based)
    number_of_blocks: int  # 1 byte - Total blocks to read
    response_options: int = 0  # 1 byte - Response options (optional)


@dataclass
class ReadMultiblockResponse:
    """Read Multiblock command response"""

    error_code: int  # 1 byte - Error code
    address: bytes  # 8 bytes - Tag serial number
    first_block_number: Optional[int] = None  # 1 byte - First block (new style)
    number_of_blocks: Optional[int] = None  # 1 byte - Number of blocks returned
    blocks: list[BlockData] = None  # Variable - Block data


# Write Multiblock (0x04) - Write block(s) data to a specific tag
@dataclass
class WriteMultiblockRequest:
    """Write Multiblock command request"""

    address: bytes  # 8 bytes - Tag serial number
    first_block_number: int  # 1 byte - First block to write (0-based)
    number_of_blocks: int  # 1 byte - Total blocks to write
    flags: int = 0  # 1 byte - Reserved flags (set to 0)
    block_data: list[bytes] = None  # Variable - 4-byte data for each block


@dataclass
class WriteMultiblockResponse:
    """Write Multiblock command response"""

    error_code: int  # 1 byte - Error code
    address: bytes  # 8 bytes - Tag serial number
    block_number: Optional[int] = None  # 1 byte - Block with error or last written+1


# Write Block (0x05) - Write 1 block of data to a specific tag
@dataclass
class WriteBlockRequest:
    """Write Block command request"""

    address: bytes  # 8 bytes - Tag serial number
    block_number: int  # 1 byte - Block to write (0-based)
    data: bytes  # 4 bytes - Data to write


@dataclass
class WriteBlockResponse:
    """Write Block command response"""

    error_code: int  # 1 byte - Error code
    address: bytes  # 8 bytes - Tag serial number


# Write & Lock Block (0x07) - Write/lock 1 block of data to a specific tag
@dataclass
class WriteLockBlockRequest:
    """Write & Lock Block command request"""

    address: bytes  # 8 bytes - Tag serial number
    block_number: int  # 1 byte - Block to write and lock (0-based)
    data: bytes  # 4 bytes - Data to write


@dataclass
class WriteLockBlockResponse:
    """Write & Lock Block command response"""

    error_code: int  # 1 byte - Error code
    address: bytes  # 8 bytes - Tag serial number


# Lock Block (0x08) - Lock 1 block of data on a specific tag
@dataclass
class LockBlockRequest:
    """Lock Block command request"""

    address: bytes  # 8 bytes - Tag serial number
    block_number: int  # 1 byte - Block to lock (0-based)


@dataclass
class LockBlockResponse:
    """Lock Block command response"""

    error_code: int  # 1 byte - Error code
    address: bytes  # 8 bytes - Tag serial number


# Get AFI (0x0A) - Read AFI from a specific tag
@dataclass
class GetAFIRequest:
    """Get AFI command request"""

    address: bytes  # 8 bytes - Tag serial number


@dataclass
class GetAFIResponse:
    """Get AFI command response"""

    error_code: int  # 1 byte - Error code
    address: bytes  # 8 bytes - Tag serial number
    afi: int  # 1 byte - Application Family Identifier value


# Write AFI (0x09) - Write AFI to a specific tag
@dataclass
class WriteAFIRequest:
    """Write AFI command request"""

    address: bytes  # 8 bytes - Tag serial number
    afi: int  # 1 byte - AFI value to write


@dataclass
class WriteAFIResponse:
    """Write AFI command response"""

    error_code: int  # 1 byte - Error code
    address: bytes  # 8 bytes - Tag serial number


# Lock AFI (0x06) - Lock AFI on a specific tag
@dataclass
class LockAFIRequest:
    """Lock AFI command request"""

    address: bytes  # 8 bytes - Tag serial number


@dataclass
class LockAFIResponse:
    """Lock AFI command response"""

    error_code: int  # 1 byte - Error code
    address: bytes  # 8 bytes - Tag serial number


# Check EAS (0x03) - Read EAS from a specific tag
@dataclass
class CheckEASRequest:
    """Check EAS command request"""

    address: bytes  # 8 bytes - Tag serial number


@dataclass
class CheckEASResponse:
    """Check EAS command response"""

    error_code: int  # 1 byte - Error code
    address: bytes  # 8 bytes - Tag serial number
    eas: int  # 1 byte - EAS value (1 or 0)


# EAS Control (0x0C) - Write EAS to a specific tag
@dataclass
class EASControlRequest:
    """EAS Control command request"""

    address: bytes  # 8 bytes - Tag serial number
    eas_value: int  # 1 byte - EAS value to set (1 or 0)


@dataclass
class EASControlResponse:
    """EAS Control command response"""

    error_code: int  # 1 byte - Error code
    address: bytes  # 8 bytes - Tag serial number


# Get DSFID (0x0F) - Read DSFID from a specific tag
@dataclass
class GetDSFIDRequest:
    """Get DSFID command request"""

    address: bytes  # 8 bytes - Tag serial number


@dataclass
class GetDSFIDResponse:
    """Get DSFID command response"""

    error_code: int  # 1 byte - Error code
    address: bytes  # 8 bytes - Tag serial number
    dsfid: int  # 1 byte - Data Storage Format Identifier value


# Write DSFID (0x0B) - Write DSFID to a specific tag
@dataclass
class WriteDSFIDRequest:
    """Write DSFID command request"""

    address: bytes  # 8 bytes - Tag serial number
    dsfid: int  # 1 byte - DSFID value to write


@dataclass
class WriteDSFIDResponse:
    """Write DSFID command response"""

    error_code: int  # 1 byte - Error code
    address: bytes  # 8 bytes - Tag serial number


# Lock DSFID (0x0E) - Lock DSFID on a specific tag
@dataclass
class LockDSFIDRequest:
    """Lock DSFID command request"""

    address: bytes  # 8 bytes - Tag serial number


@dataclass
class LockDSFIDResponse:
    """Lock DSFID command response"""

    error_code: int  # 1 byte - Error code
    address: bytes  # 8 bytes - Tag serial number


# Tag Info (0x0D) - Get many things from a specific tag
@dataclass
class TagInfoRequest:
    """Tag Info command request"""

    address: bytes  # 8 bytes - Tag serial number
    info_requested: int  # 1 byte - Bitfield of requested information


@dataclass
class TagInfoResponse:
    """Tag Info command response"""

    error_code: int  # 1 byte - Error code
    address: bytes  # 8 bytes - Tag serial number
    info_avail: int  # 1 byte - Bitfield of available information
    dsfid: Optional[int] = None  # 1 byte - DSFID (when bit 0 set in info_avail)
    afi: Optional[int] = None  # 1 byte - AFI (when bit 1 set in info_avail)
    block_size_minus_one: Optional[int] = None  # 1 byte - Tag block size-1 (when bit 2 set)
    total_blocks_minus_one: Optional[int] = None  # 1 byte - Tag total blocks-1 (when bit 2 set)
    ic_ref: Optional[bytes] = None  # 2 bytes - IC Reference (when bit 3 set in info_avail)


def validate_rfid_response(
    data: bytes, expected_command_code: Optional[int] = None
) -> RFIDResponseValidation:
    """
    Common validation method for RFID reader protocol responses.

    Validates the basic structure and integrity of responses from the 3M RFID Reader
    according to the protocol specification:
    - Start Byte (0xD6) - 1 byte - Mandatory
    - Length - 2 bytes - Mandatory
    - Command Code - 1 byte - Mandatory
    - Error Code - 1 byte - Mandatory (for responses)
    - [Conditional Fields] - Variable length
    - BCC (CRC) - 2 bytes - Mandatory

    Args:
        data: Raw response bytes from RFID reader
        expected_command_code: Optional command code to validate against (None to skip validation)

    Returns:
        RFIDResponseValidation: Validation result containing:
            - is_valid: True if response passes all validation checks
            - command_code: Extracted command code from response
            - error_code: Extracted error code from response
            - payload_data: Response payload excluding start byte, length, and CRC
            - error_message: Description of validation failure if is_valid is False

    Validation checks performed:
        1. Minimum message length (6 bytes: start + length + command + error + crc)
        2. Start byte validation (must be 0xD6)
        3. Length field consistency with actual message length
        4. CRC checksum validation (calculated on all bytes except start byte)
        5. Optional command code validation if expected_command_code provided

    Example:
        >>> response_data = bytes.fromhex("D60008110A050219E23B")
        >>> result = validate_rfid_response(response_data, 0x11)
        >>> if result.is_valid:
        ...     print(f"Command: {result.command_code:02X}, Error: {result.error_code:02X}")
    """

    # Check minimum message length (start + length + command + error + crc = 6 bytes)
    if not data or len(data) < 6:
        return RFIDResponseValidation(
            is_valid=False,
            error_message=f"Response too short: {len(data) if data else 0} bytes (minimum 6 required)",
        )

    # Validate start byte (0xD6)
    if data[0] != 0xD6:
        return RFIDResponseValidation(
            is_valid=False, error_message=f"Invalid start byte: 0x{data[0]:02X} (expected 0xD6)"
        )

    # Extract and validate length field (bytes 1-2, big-endian)
    declared_length = (data[1] << 8) | data[2]
    actual_payload_length = len(data) - 3  # Total length minus start byte and length field

    if declared_length != actual_payload_length:
        return RFIDResponseValidation(
            is_valid=False,
            error_message=f"Length mismatch: declared {declared_length}, actual {actual_payload_length}",
        )

    # Extract command code and error code
    command_code = data[3]
    error_code = data[4]

    # Validate command code if expected
    if expected_command_code is not None and command_code != expected_command_code:
        return RFIDResponseValidation(
            is_valid=False,
            command_code=command_code,
            error_code=error_code,
            error_message=f"Command code mismatch: received 0x{command_code:02X}, "
            f"expected 0x{expected_command_code:02X}",
        )

    # Extract and validate CRC (last 2 bytes, big-endian)
    if len(data) < 2:
        return RFIDResponseValidation(
            is_valid=False,
            command_code=command_code,
            error_code=error_code,
            error_message="Message too short for CRC",
        )

    received_crc = (data[-2] << 8) | data[-1]

    # Calculate CRC on all bytes except start byte (as per protocol specification)
    payload_for_crc = data[1:-2]  # Exclude start byte and CRC bytes
    calculated_crc = crc_ccitt(payload_for_crc)

    if received_crc != calculated_crc:
        return RFIDResponseValidation(
            is_valid=False,
            command_code=command_code,
            error_code=error_code,
            error_message=f"CRC mismatch: received 0x{received_crc:04X}, calculated 0x{calculated_crc:04X}",
        )

    # Extract payload data (everything except start byte, length field, and CRC)
    payload_data = data[3:-2] if len(data) > 5 else bytes()

    return RFIDResponseValidation(
        is_valid=True, command_code=command_code, error_code=error_code, payload_data=payload_data
    )


def parseReadVersionResponse(data: bytes) -> Optional[ReaderVersionResponse]:
    """
    parseReadVersionResponse parses a Reader Version response from RFID reader

    Uses common validation method and returns structured dataclass instead of dictionary.

    :param data: bytes the response data to be parsed
    :return: ReaderVersionResponse dataclass with parsed data, or None if parsing fails
    """
    try:
        # Validate response structure and extract common fields
        validation = validate_rfid_response(data, Command.NORM_READER_VERSION.value)

        if not validation.is_valid:
            sentry_sdk.capture_message(
                f"Reader Version response validation failed: {validation.error_message}"
            )
            return None

        # Check if we have enough payload data for version information (4 bytes after command/error)
        if len(validation.payload_data) < 6:  # command + error + 4 version bytes
            sentry_sdk.capture_message(
                f"Reader Version response too short: {len(validation.payload_data)} bytes"
            )
            return None

        # Extract version data from payload (after command code and error code)
        vendor_id = int(validation.payload_data[2])  # Byte after error code
        major_value = int(validation.payload_data[3])
        minor_value = int(validation.payload_data[4])
        build_version = int(validation.payload_data[5])

        return ReaderVersionResponse(
            error_code=validation.error_code,
            vendor_id=vendor_id,
            major_value=major_value,
            minor_value=minor_value,
            build_version=build_version,
        )

    except Exception as e:
        sentry_sdk.capture_exception(error=e)
        return None


def parseReadBlockUIDResponse(data: bytes) -> Optional[ReadBlockUIDResponse]:
    """
    parseReadBlockUIDResponse parses a Read Block UID response from RFID reader

    Uses common validation method and returns structured dataclass instead of dictionary.

    :param data: bytes the response data to be parsed
    :return: ReadBlockUIDResponse dataclass with parsed data, or None if parsing fails
    """
    try:
        # Validate response structure and extract common fields
        validation = validate_rfid_response(data, Command.NORM_READ_BLOCK_UID.value)

        if not validation.is_valid:
            sentry_sdk.capture_message(
                f"Read Block UID response validation failed: {validation.error_message}"
            )
            return None

        # Check minimum payload length (command + error + afi + response_options + num_tags = 5 bytes)
        if len(validation.payload_data) < 5:
            sentry_sdk.capture_message(
                f"Read Block UID response too short: {len(validation.payload_data)} bytes"
            )
            return None

        # Extract response fields from payload (after command code and error code)
        afi = validation.payload_data[2]  # AFI field
        response_options = validation.payload_data[3]  # Response options field
        num_tags = validation.payload_data[4]  # Number of transponders

        # Parse tag data - each tag has DSFID (1 byte) + Address (8 bytes) = 9 bytes per tag
        # But according to spec, DSFID is only returned if bit1 is set in response_options
        # Address is returned if bit0 is set in response_options
        tags = []
        tag_data_start = 5  # Start of tag data in payload

        # Determine bytes per tag based on response options
        bytes_per_tag = 0
        if response_options & 0x02:  # Bit 1: DSFID requested
            bytes_per_tag += 1
        if response_options & 0x01:  # Bit 0: Address requested
            bytes_per_tag += 8

        # Check if we have enough data for all tags
        expected_tag_data_length = num_tags * bytes_per_tag
        available_tag_data_length = len(validation.payload_data) - tag_data_start

        if available_tag_data_length < expected_tag_data_length:
            sentry_sdk.capture_message(
                f"Read Block UID insufficient tag data: expected {expected_tag_data_length}, "
                f"available {available_tag_data_length}"
            )
            return None

        # Parse each tag
        for i in range(num_tags):
            tag_offset = tag_data_start + (i * bytes_per_tag)

            dsfid = 0
            address = bytes()

            current_offset = tag_offset

            # Extract DSFID if requested (bit 1 set in response_options)
            if response_options & 0x02:
                dsfid = validation.payload_data[current_offset]
                current_offset += 1

            # Extract Address if requested (bit 0 set in response_options)
            if response_options & 0x01:
                address = validation.payload_data[current_offset : current_offset + 8]
                current_offset += 8

            tags.append(TagData(dsfid=dsfid, address=address))

        return ReadBlockUIDResponse(
            error_code=validation.error_code,
            afi=afi,
            response_options=response_options,
            num_tags=num_tags,
            tags=tags,
        )

    except Exception as e:
        sentry_sdk.capture_exception(error=e)
        return None


def parseReadMultiblockResponse(
    data: bytes, style: ResponseStyle = ResponseStyle.NEW_WITHOUT_LOCK_INFORMATION
) -> Optional[ReadMultiblockResponse]:
    """
    parseReadMultiblockResponse parses a Read Multiblock response from RFID reader

    Uses common validation method and returns structured dataclass. Parses according
    to the specified style as per 3M RFID specification:

    Old style: Number of Blocks, then [Block Number, Lock/Err, 4B Data] (6B per block)
    New style: First Block, Number of Blocks, then [Lock/Err, 4B Data] (5B per block)

    :param data: bytes the response data to be parsed
    :param style: ResponseStyle the response style to use (default: ResponseStyle.NEW_WITHOUT_LOCK_INFORMATION)
    :return: ReadMultiblockResponse dataclass with parsed data, or None if parsing fails
    """
    try:
        # Validate response structure and extract common fields
        validation = validate_rfid_response(data, Command.ADDR_READ_MULTIBLOCK.value)

        if not validation.is_valid:
            sentry_sdk.capture_message(
                f"Read Multiblock response validation failed: {validation.error_message}"
            )
            return None

        # Check minimum payload length (command + error + address + 2 bytes for block info)
        if len(validation.payload_data) < 12:
            sentry_sdk.capture_message(
                f"Read Multiblock response too short: {len(validation.payload_data)} bytes"
            )
            return None

        # Extract address (8 bytes after command and error code)
        address = validation.payload_data[2:10]

        # Parse the response data after address
        remaining_data = validation.payload_data[10:]

        if len(remaining_data) < 2:
            sentry_sdk.capture_message("Read Multiblock response missing block information")
            return None

        first_block_number = None
        number_of_blocks = 0
        blocks = []

        if style == ResponseStyle.NEW_WITHOUT_LOCK_INFORMATION:
            # New style: First Block Number, Number of Blocks, then [4B Data]
            first_block_number = remaining_data[0]
            number_of_blocks = remaining_data[1]

            for i in range(number_of_blocks):
                block_offset = 2 + (i * 4)
                if block_offset + 4 <= len(remaining_data):
                    block_number = first_block_number + i
                    block_data = remaining_data[block_offset : block_offset + 4]
                    blocks.append(
                        BlockData(block_number=block_number, lock_status=0, data=block_data)
                    )
        elif style == ResponseStyle.NEW_WITH_LOCK_INFORMATION:
            # New style: First Block Number, Number of Blocks, then [Lock/Err, 4B Data]
            first_block_number = remaining_data[0]
            number_of_blocks = remaining_data[1]

            for i in range(number_of_blocks):
                block_offset = 2 + (i * 5)
                if block_offset + 5 <= len(remaining_data):
                    block_number = first_block_number + i
                    lock_status = remaining_data[block_offset]
                    block_data = remaining_data[block_offset + 1 : block_offset + 5]
                    blocks.append(
                        BlockData(
                            block_number=block_number, lock_status=lock_status, data=block_data
                        )
                    )
        else:
            # Old style: Number of Blocks, then [Block Number, Lock/Err, 4B Data]
            number_of_blocks = remaining_data[0]

            # Use available data for parsing
            actual_blocks = min(number_of_blocks, (len(remaining_data) - 1) // 6)

            for i in range(actual_blocks):
                block_offset = 1 + (i * 6)
                if block_offset + 6 <= len(remaining_data):
                    block_number = remaining_data[block_offset]
                    lock_status = remaining_data[block_offset + 1]
                    block_data = remaining_data[block_offset + 2 : block_offset + 6]

                    blocks.append(
                        BlockData(
                            block_number=block_number, lock_status=lock_status, data=block_data
                        )
                    )

        return ReadMultiblockResponse(
            error_code=validation.error_code,
            address=address,
            first_block_number=first_block_number,
            number_of_blocks=len(blocks),
            blocks=blocks,
        )

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
                                    f"{ver.vendor_id} {ver.major_value}."
                                    f"{ver.minor_value}.{ver.build_version}"
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
                        if uid_res:
                            if uid_res.num_tags == 1 and uid_res.afi == 0:
                                self.active_address = uid_res.tags[0].address.hex()
                                self.state = ReaderState.SINGLE_TAG_READ
                            elif uid_res.num_tags > 1:
                                self.active_address = None
                                self.active_tag = None
                                self.state = ReaderState.MULTIPLE_TAGS_DETECTED
                            else:
                                self.active_address = None
                                self.active_tag = None
                                self.state = ReaderState.READER_CONNECTED
                        else:
                            self.active_address = None
                            self.active_tag = None
                            self.state = ReaderState.READER_CONNECTED
                    else:
                        self.active_address = None
                        self.active_tag = None
                        self.state = ReaderState.NO_READER_CONNECTED

                case ReaderState.SINGLE_TAG_READ:
                    cmd = build_command_hex(
                        Command.ADDR_READ_MULTIBLOCK.value, f"{self.active_address}000805"
                    )
                    self.send_data(bytes.fromhex(cmd))
                    time.sleep(self.reader_wait)
                    resp = self.read_data()
                    try:
                        response = parseReadMultiblockResponse(
                            resp, ResponseStyle.NEW_WITH_LOCK_INFORMATION
                        )
                        if response.number_of_blocks > 0:
                            helmet_rfid_tag = HelmetRfidTag(
                                b"".join(block.data for block in response.blocks)
                            )
                            if helmet_rfid_tag.welformed_data:
                                self.active_tag = helmet_rfid_tag
                                self.state = ReaderState.TAG_PARSED
                            else:
                                self.state = ReaderState.UNKNOWN_TAG
                                self.active_tag = None
                        else:
                            self.active_address = None
                            self.active_tag = None
                            self.state = ReaderState.READER_ERROR
                    except Exception:
                        self.state = ReaderState.READER_ERROR
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
