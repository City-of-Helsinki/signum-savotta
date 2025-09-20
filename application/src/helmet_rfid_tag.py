"""
Parsing Finnish RFID tags according to ISO 28560
"""

from dataclasses import dataclass
from enum import Enum

iso_iec_latch_shift_values = [
    "Latch upper",
    "Shift upper",
    "Latch lower",
    "Shift lower",
    "Latch numeric",
    "Shift numeric",
]

iso_iec_4bit_numeric_encoding = {
    "0000": "0",
    "0001": "1",
    "0010": "2",
    "0011": "3",
    "0100": "4",
    "0101": "5",
    "0110": "6",
    "0111": "7",
    "1000": "8",
    "1001": "9",
    "1010": "-",
    "1011": ":",
    "1100": "Latch upper",
    "1101": "Shift upper",
    "1110": "Latch lower",
    "1111": "Shift lower",
}

iso_iec_5bit_uppercase_encoding_dict = {
    "00000": "-",
    "00001": "A",
    "00010": "B",
    "00011": "C",
    "00100": "D",
    "00101": "E",
    "00110": "F",
    "00111": "G",
    "01000": "H",
    "01001": "I",
    "01010": "J",
    "01011": "K",
    "01100": "L",
    "01101": "M",
    "01110": "N",
    "01111": "O",
    "10000": "P",
    "10001": "Q",
    "10010": "R",
    "10011": "S",
    "10100": "T",
    "10101": "U",
    "10110": "V",
    "10111": "W",
    "11000": "X",
    "11001": "Y",
    "11010": "Z",
    "11011": ":",
    "11100": "Latch lower",
    "11101": "Shift lower",
    "11110": "Latch numeric",
    "11111": "Shift numeric",
}

iso_iec_5bit_lowercase_encoding_dict = {
    "00000": "-",
    "00001": "a",
    "00010": "b",
    "00011": "c",
    "00100": "d",
    "00101": "e",
    "00110": "f",
    "00111": "g",
    "01000": "h",
    "01001": "i",
    "01010": "j",
    "01011": "k",
    "01100": "l",
    "01101": "m",
    "01110": "n",
    "01111": "o",
    "10000": "p",
    "10001": "q",
    "10010": "r",
    "10011": "s",
    "10100": "t",
    "10101": "u",
    "10110": "v",
    "10111": "w",
    "11000": "x",
    "11001": "y",
    "11010": "z",
    "11011": "/",
    "11100": "Latch upper",
    "11101": "Shift upper",
    "11110": "Latch numeric",
    "11111": "Shift numeric",
}

iso_iec_6bit_dict = {
    "000000": "@",
    "000001": "A",
    "000010": "B",
    "000011": "C",
    "000100": "D",
    "000101": "E",
    "000110": "F",
    "000111": "G",
    "001000": "H",
    "001001": "I",
    "001010": "J",
    "001011": "K",
    "001100": "L",
    "001101": "M",
    "001110": "N",
    "001111": "O",
    "010000": "P",
    "010001": "Q",
    "010010": "R",
    "010011": "S",
    "010100": "T",
    "010101": "U",
    "010110": "V",
    "010111": "W",
    "011000": "X",
    "011001": "Y",
    "011010": "Z",
    "011011": "[",
    "011100": "\\",
    "011101": "]",
    "011110": "^",
    "011111": "_",
    "100000": " ",
    "100001": "EOT",
    "100010": "Reserved",
    "100011": "FS",
    "100100": "US",
    "100101": "Reserved",
    "100110": "Reserved",
    "100111": "Reserved",
    "101000": "(",
    "101001": ")",
    "101010": "*",
    "101011": "+",
    "101100": ",",
    "101101": "-",
    "101110": ".",
    "101111": "/",
    "110000": "0",
    "110001": "1",
    "110010": "2",
    "110011": "3",
    "110100": "4",
    "110101": "5",
    "110110": "6",
    "110111": "7",
    "111000": "8",
    "111001": "9",
    "111010": ":",
    "111011": ";",
    "111100": "<",
    "111101": "=",
    "111110": ">",
    "111111": "?",
}

iso_iec_7bit_us_ascii = {f"{i:07b}": chr(i) for i in range(128)}

type_of_usage_map = {
    "0": {
        "class": "Acquisition item",
        "sub-qualifiers": {
            "0": "Acquisition item, unspecified",
            "1": "Acquisition item, for automated process",
            "2": "Acquisition item, for manual process",
            "3456789ABCDEF": "For future use within the class",
        },
    },
    "1": {
        "class": "Item for circulation",
        "sub-qualifiers": {
            "0": "Circulating item, unspecified",
            "1": "Circulating item, for automatic sorting",
            "2": "Circulating item, not for automatic sorting",
            "3": "Circulating item, not for issue while offline",
            "4": "Circulating item, not for return while offline",
            "5": "Circulating item, not for issue or return while offline",
            "6789ABCDEF": "For future use within the class",
        },
    },
    "2": {
        "class": "Item Not For Circulation",
        "sub-qualifiers": {
            "0": "Non-circulating item, unspecified",
            "1234567890ABCDEF": "For future use within the class",
        },
    },
    "3": {
        "class": "For Local Use",
        "sub-qualifiers": {
            "0": "For local use, unspecified sub-class",
            "1234567890ABCDEF": "For future use within the class",
        },
    },
    "4": {
        "class": "For Local Use",
        "sub-qualifiers": {
            "0": "For local use, unspecified sub-class",
            "1234567890ABCDEF": "For future use within the class",
        },
    },
    "5": {
        "class": "For Future Use",
        "sub-qualifiers": {
            "0": "For future use, unspecified sub-class",
            "1234567890ABCDEF": "For future use within the class",
        },
    },
    "6": {
        "class": "No information about usage on the tag",
        "sub-qualifiers": {
            "0": """If the type of usage data element is locked with a type of usage,
            which can change over time, it should be encoded as a 6.""",
            "1234567890ABCDEF": "Not to be used",
        },
    },
    "7": {
        "class": "Discarded item",
        "sub-qualifiers": {
            "0": "Discarded item, unspecified",
            "1": "Discarded item, for sale",
            "2": "Discarded item, sold",
            "3": "Discarded item, for disposal",
            "456789ABCDEF": "For future use within the class",
        },
    },
    "8": {
        "class": "Patron card",
        "sub-qualifiers": {
            "0": "Patron card, unspecified",
            "1": "Patron card, adult borrower",
            "2": "Patron card, young adult borrower",
            "3": "Patron card, standard child borrower",
            "456789ABCDEF": "For future use within the class",
        },
    },
    "9": {
        "class": "Library equipment",
        "sub-qualifiers": {
            "0": "Library equipment, unspecified",
            "1": "Personal computer",
            "2": "Video projector",
            "3": "Overhead projector",
            "4": "Whiteboard",
            "56789ABCDEF": "For future use within the class",
        },
    },
    "A": {
        "class": "For Future Use",
        "sub-qualifiers": {
            "0": "For future use, unspecified sub-class",
            "1234567890ABCDEF": "For future use within the class",
        },
    },
    "B": {
        "class": "For Future Use",
        "sub-qualifiers": {
            "0": "For future use, unspecified sub-class",
            "1234567890ABCDEF": "For future use within the class",
        },
    },
    "C": {
        "class": "For Future Use",
        "sub-qualifiers": {
            "0": "For future use, unspecified sub-class",
            "1234567890ABCDEF": "For future use within the class",
        },
    },
    "D": {
        "class": "For Future Use",
        "sub-qualifiers": {
            "0": "For future use, unspecified sub-class",
            "1234567890ABCDEF": "For future use within the class",
        },
    },
    "E": {
        "class": "For Future Use",
        "sub-qualifiers": {
            "0": "For future use, unspecified sub-class",
            "1234567890ABCDEF": "For future use within the class",
        },
    },
    "F": {
        "class": "For Future Use",
        "sub-qualifiers": {
            "0": "For future use, unspecified sub-class",
            "1234567890ABCDEF": "For future use within the class",
        },
    },
}


def decode_iso_iec_4bit_5bit(binary_string, starting_dict):
    """
    decode_iso_iec_4bit_5bit
    """
    result = []
    shift = False

    bs_to_process = binary_string
    active_dict = starting_dict
    latch_dict = starting_dict
    shift_dict = starting_dict

    # FIXME: Should be the minimum amount of bits for the used dictionary
    while len(bs_to_process) > 3:
        if shift:
            active_dict = shift_dict
        else:
            active_dict = latch_dict

        shift = False
        matched = False

        for key in active_dict:
            if bs_to_process[0 : len(key)] == key:
                matched = True
                if active_dict[key] not in iso_iec_latch_shift_values:
                    result.append(active_dict[key])
                elif "Latch" in active_dict[key]:
                    if "upper" in active_dict[key]:
                        latch_dict = iso_iec_5bit_uppercase_encoding_dict
                    elif "lower" in active_dict[key]:
                        latch_dict = iso_iec_5bit_lowercase_encoding_dict
                    else:
                        latch_dict = iso_iec_4bit_numeric_encoding
                elif "Shift" in active_dict[key]:
                    if "upper" in active_dict[key]:
                        shift_dict = iso_iec_5bit_uppercase_encoding_dict
                    elif "lower" in active_dict[key]:
                        shift_dict = iso_iec_5bit_lowercase_encoding_dict
                    else:
                        shift_dict = iso_iec_4bit_numeric_encoding
                    shift = True
                bs_to_process = bs_to_process[len(key) :]
                break

        # Break if no match found to prevent infinite loop
        if not matched:
            break

    return "".join(result)


def decode_with_dict(binary_string, dictonary, min_length):
    """
    decode_with_dict
    """
    result = []
    bs_to_process = binary_string

    # FIXME: use greater or equal instead?
    while len(bs_to_process) > min_length:
        for key in dictonary:
            if bs_to_process[0 : len(key)] == key:
                result.append(dictonary[key])
                bs_to_process = bs_to_process[len(key) :]
    return "".join(result)


def decode_iso_iec_8859_1(binary_string):
    """
    decode_iso_iec_8859_1
    """
    bytes = int(binary_string, 2).to_bytes((len(binary_string) + 7) // 8, byteorder="big")
    return bytes.decode("iso-8859-1")


def decode_utf8_binary(binary_string):
    """
    decode_utf8_binarys
    """
    bytes_list = [binary_string[i : i + 8] for i in range(0, len(binary_string), 8)]
    chars = []
    i = 0
    while i < len(bytes_list):
        byte = bytes_list[i]
        if byte.startswith("0"):  # 1-byte
            code_point = int(byte, 2)
            i += 1
        elif byte.startswith("110"):  # 2-byte
            code_point = (int(byte[3:], 2) << 6) | int(bytes_list[i + 1][2:], 2)
            i += 2
        elif byte.startswith("1110"):  # 3-byte
            code_point = (
                (int(byte[4:], 2) << 12)
                | (int(bytes_list[i + 1][2:], 2) << 6)
                | int(bytes_list[i + 2][2:], 2)
            )
            i += 3
        elif byte.startswith("11110"):  # 4-byte
            code_point = (
                (int(byte[5:], 2) << 18)
                | (int(bytes_list[i + 1][2:], 2) << 12)
                | (int(bytes_list[i + 2][2:], 2) << 6)
                | int(bytes_list[i + 3][2:], 2)
            )
            i += 4
        else:
            raise ValueError("Invalid UTF-8 byte sequence")
        chars.append(chr(code_point))
    return "".join(chars)


class Oid(Enum):
    """
    Oid is an enumeration for the 4-bit oid values plus one representing an empty block
    Note that values 27 to 31 are unused according to spec
    """

    EMPTY = 0
    PRIMARY_ITEM_IDENTIFIER = 1
    CONTENT_PARAMETER = 2
    OWNER_LIBRARY_ISIL = 3
    SET_INFORMATION = 4
    TYPE_OF_USAGE = 5
    SHELF_LOCATION = 6
    ONIX_MEDIA_FORMAT = 7
    MARC_MEDIA_FORMAT = 8
    SUPPLIER_IDENTIFIER = 9
    ORDER_NUMBER = 10
    ILL_BORROWING_INSTITUTION_ISIL = 11
    ILL_BORROWING_TRANSACTION_NUMBER = 12
    GS1_PRODUCT_IDENTIFIER = 13
    ALTERNATIVE_UNIQUE_ITEM_IDENTIFIER = 14
    LOCAL_DATA_A = 15
    LOCAL_DATA_B = 16
    TITLE = 17
    PRODUCT_IDENTIFIER_LOCAL = 18
    MEDIA_FORMAT_OTHER = 19
    SUPPLY_CHAIN_STAGE = 20
    SUPPLIER_INVOICE_NUMBER = 21
    ALTERNATIVE_ITEM_IDENTIFIER = 22
    ALTERNATIVE_OWNER_LIBRARY_IDENTIFIER = 23
    SUBSIDIARY_OF_AN_OWNER_LIBRARY = 24
    ALTERNATIVE_ILL_BORROWING_INSTITUTION = 25
    LOCAL_DATA_C = 26


class Encoding(Enum):
    """
    Endcoding in and enumeration for the 3-bit encoding values plus one representing unknown compaction.
    """

    APPLICATION_SPECIFIC = 0
    UNSIGNED_BIG_ENDIAN_INTEGER = 1
    NUMERIC_STRING = 2
    ISO_IEC_5_BIT_CODE_UPPERCASE_ALPHABETIC = 3
    ISO_IEC_6_BIT_CODE = 4
    ISO_IEC_7_BIT_CODE_US_ASCII = 5
    OCTET_STRING_ISO_IEC_8859_1 = 6
    UTF_8_STRING_ISO_IEC_10646 = 7
    UNKNOWN_COMPACTION = 8


@dataclass(repr=True, eq=True, order=False, unsafe_hash=False, frozen=False)
class HelmetRfidTag:
    """
    HelmetRfidTag represents the RFID tag
    """

    welformed_data = False

    primary_item_identifier = None
    content_parameter = None
    owner_library_isil = None
    set_information = None
    type_of_usage = None
    shelf_location = None
    onix_media_format = None
    marc_media_format = None
    supplier_identifier = None
    order_number = None
    ill_borrowing_institution_isil = None
    ill_borrowing_transaction_number = None
    gs1_product_identifier = None
    alternative_unique_item_identifier = None
    local_data_a = None
    local_data_b = None
    title = None
    product_identifier_local = None
    media_format_other = None
    supply_chain_stage = None
    supplier_invoice_number = None
    alternative_item_identifier = None
    alternative_owner_library_identifier = None
    subsidiary_of_an_owner_library = None
    alternative_ill_borrowing_institution = None
    local_data_c = None

    def __init__(self, data_bytes):
        if data_bytes is not None:
            self.parse_data(data_bytes)

    # FIXME: Unit tests for this code
    def decode(self, encoding, data, oid):
        """
        decode decodes the RFID tag data bitmap
        """
        match (encoding, oid):
            case (Encoding.APPLICATION_SPECIFIC, Oid.CONTENT_PARAMETER):
                expected_oids = []
                relative_oids = [
                    3,
                    4,
                    5,
                    6,
                    7,
                    8,
                    9,
                    10,
                    11,
                    12,
                    13,
                    14,
                    15,
                    16,
                    17,
                    18,
                    19,
                    20,
                    21,
                    22,
                    23,
                    24,
                    25,
                    26,
                    27,
                    28,
                    29,
                    30,
                    31,
                    32,
                ]
                for index, bit in enumerate(data):
                    if bit == "1":
                        expected_oids.append(relative_oids[index])
                return expected_oids
            case (Encoding.APPLICATION_SPECIFIC, Oid.OWNER_LIBRARY_ISIL):
                return decode_iso_iec_4bit_5bit(data, iso_iec_5bit_uppercase_encoding_dict)
            case (Encoding.APPLICATION_SPECIFIC, Oid.TYPE_OF_USAGE):
                try:
                    class_qualifier = format(int(data[0:4], 2), "X")
                    sub_qualifier = format(int(data[4:8], 2), "X")
                    cls = type_of_usage_map[class_qualifier]["class"]
                    sub_qualifiers = type_of_usage_map[class_qualifier]["sub-qualifiers"]
                    for key in sub_qualifiers:
                        if sub_qualifier in key:
                            return (cls, sub_qualifiers[key])
                except Exception:
                    return None
                return None
            case (Encoding.APPLICATION_SPECIFIC, Oid.GS1_PRODUCT_IDENTIFIER):
                return int.from_bytes(
                    int(data, 2).to_bytes((len(data) + 7) // 8), byteorder="big", signed=False
                )
            case (Encoding.APPLICATION_SPECIFIC, _):
                return f"unhandled app specific encoding, oid: {oid}, data: {int.from_bytes(
                    int(data, 2).to_bytes((len(data) + 7) // 8), byteorder="big", signed=False
                )}"
            case (Encoding.UNSIGNED_BIG_ENDIAN_INTEGER, _):
                return int.from_bytes(
                    int(data, 2).to_bytes((len(data) + 7) // 8), byteorder="big", signed=False
                )
            case (Encoding.NUMERIC_STRING, _):
                return decode_iso_iec_4bit_5bit(data, iso_iec_4bit_numeric_encoding)
            case (Encoding.ISO_IEC_5_BIT_CODE_UPPERCASE_ALPHABETIC, _):
                return decode_with_dict(data, iso_iec_5bit_uppercase_encoding_dict)
            case (Encoding.ISO_IEC_6_BIT_CODE, _):
                return decode_with_dict(data, iso_iec_6bit_dict, 5)
            case (Encoding.ISO_IEC_7_BIT_CODE_US_ASCII, _):
                return decode_with_dict(data, iso_iec_7bit_us_ascii, 6)
            case (Encoding.OCTET_STRING_ISO_IEC_8859_1, _):
                return decode_iso_iec_8859_1(data)
            case (Encoding.UTF_8_STRING_ISO_IEC_10646, _):
                return decode_utf8_binary(data)
            case (Encoding.UNKNOWN_COMPACTION, _):
                return f"UNKNOWN_COMPACTION, data: {data}"
            case (_, _):  # Unknown compaction
                return f"unknown encoding: {encoding}, data: {data}"

    # FIXME: Unit tests for this code.
    def parse_data(self, data_bytes):
        """
        parse_data parses and validates the RFID tag data block
        """
        binary_string = "".join(format(byte, "08b") for byte in data_bytes)
        length = 0
        self.welformed_data = True
        try:
            while len(binary_string) > 0 and len(binary_string) >= 16:
                offset = binary_string[0]

                encoding = Encoding(int(binary_string[1:4], 2))
                oid = Oid(int(binary_string[4:8], 2))

                padding = 0
                if offset == "1":
                    padding = int(binary_string[8:16], 2)

                starting_position = 8 if offset == "1" else 0
                try:
                    length = int(binary_string[starting_position + 8 : starting_position + 16], 2)
                except Exception:
                    length = 0
                data = binary_string[starting_position + 16 : starting_position + 16 + length * 8]
                if data != "":
                    try:
                        value = self.decode(encoding=encoding, data=data, oid=oid)
                    except Exception as e:
                        print(e)
                    match oid:
                        case Oid.PRIMARY_ITEM_IDENTIFIER:
                            self.primary_item_identifier = value
                        case Oid.CONTENT_PARAMETER:
                            self.content_parameter = value
                        case Oid.OWNER_LIBRARY_ISIL:
                            self.owner_library_isil = value
                        case Oid.SET_INFORMATION:
                            self.set_information = value
                        case Oid.TYPE_OF_USAGE:
                            self.type_of_usage = value
                        case Oid.SHELF_LOCATION:
                            self.shelf_location = value
                        case Oid.ONIX_MEDIA_FORMAT:
                            self.onix_media_format = value
                        case Oid.MARC_MEDIA_FORMAT:
                            self.marc_media_format = value
                        case Oid.SUPPLIER_IDENTIFIER:
                            self.supplier_identifier = value
                        case Oid.ORDER_NUMBER:
                            self.order_number = value
                        case Oid.ILL_BORROWING_INSTITUTION_ISIL:
                            self.ill_borrowing_institution_isil = value
                        case Oid.ILL_BORROWING_TRANSACTION_NUMBER:
                            self.ill_borrowing_transaction_number = value
                        case Oid.GS1_PRODUCT_IDENTIFIER:
                            self.gs1_product_identifier = value
                        case Oid.ALTERNATIVE_UNIQUE_ITEM_IDENTIFIER:
                            self.alternative_unique_item_identifier = value
                        case Oid.LOCAL_DATA_A:
                            self.local_data_a = value
                        case Oid.LOCAL_DATA_B:
                            self.local_data_b = value
                        case Oid.TITLE:
                            self.title = value
                        case Oid.PRODUCT_IDENTIFIER_LOCAL:
                            self.product_identifier_local = value
                        case Oid.MEDIA_FORMAT_OTHER:
                            self.media_format_other = value
                        case Oid.SUPPLY_CHAIN_STAGE:
                            self.supply_chain_stage = value
                        case Oid.SUPPLIER_INVOICE_NUMBER:
                            self.supplier_invoice_number = value
                        case Oid.ALTERNATIVE_ITEM_IDENTIFIER:
                            self.alternative_item_identifier = value
                        case Oid.ALTERNATIVE_OWNER_LIBRARY_IDENTIFIER:
                            self.alternative_owner_library_identifier = value
                        case Oid.SUBSIDIARY_OF_AN_OWNER_LIBRARY:
                            self.subsidiary_of_an_owner_library = value
                        case Oid.ALTERNATIVE_ILL_BORROWING_INSTITUTION:
                            self.alternative_ill_borrowing_institution = value
                        case Oid.LOCAL_DATA_C:
                            self.local_data_c = value
                binary_string = binary_string[(starting_position + 16 + length * 8 + padding * 8) :]
        except Exception:
            self.welformed_data = False

        if self.primary_item_identifier is None or self.primary_item_identifier == "":
            self.welformed_data = False
        """
        if self.content_parameter is None:
            self.welformed_data = False
        if self.content_parameter is not None:
            for value in self.content_parameter:
                oid = Oid(value)
                match oid:
                    case Oid.OWNER_LIBRARY_ISIL:
                        if self.owner_library_isil is None:
                            self.welformed_data = False
                        if self.owner_library_isil not in [
                            "FI-He",
                            "FI-Em",
                            "FI-Vantaa",
                            "FI-Kauni",
                        ]:
                            self.welformed_data = False
                    case Oid.SET_INFORMATION:
                        if self.set_information is None:
                            self.welformed_data = False
                    case Oid.TYPE_OF_USAGE:
                        if self.type_of_usage is None:
                            self.welformed_data = False
                    case Oid.SHELF_LOCATION:
                        if self.shelf_location is None:
                            self.welformed_data = False
                    case Oid.ONIX_MEDIA_FORMAT:
                        if self.onix_media_format is None:
                            self.welformed_data = False
                    case Oid.MARC_MEDIA_FORMAT:
                        if self.marc_media_format is None:
                            self.welformed_data = False
                    case Oid.SUPPLIER_IDENTIFIER:
                        if self.supplier_identifier is None:
                            self.welformed_data = False
                    case Oid.ORDER_NUMBER:
                        if self.order_number is None:
                            self.welformed_data = False
                    case Oid.ILL_BORROWING_INSTITUTION_ISIL:
                        if self.ill_borrowing_institution_isil is None:
                            self.welformed_data = False
                    case Oid.ILL_BORROWING_TRANSACTION_NUMBER:
                        if self.ill_borrowing_transaction_number is None:
                            self.welformed_data = False
                    case Oid.GS1_PRODUCT_IDENTIFIER:
                        if self.gs1_product_identifier is None:
                            self.welformed_data = False
                    case Oid.ALTERNATIVE_UNIQUE_ITEM_IDENTIFIER:
                        if self.alternative_unique_item_identifier is None:
                            self.welformed_data = False
                    case Oid.LOCAL_DATA_A:
                        if self.local_data_a is None:
                            self.welformed_data = False
                    case Oid.LOCAL_DATA_B:
                        if self.local_data_b is None:
                            self.welformed_data = False
                    case Oid.TITLE:
                        if self.title is None:
                            self.welformed_data = False
                    case Oid.PRODUCT_IDENTIFIER_LOCAL:
                        if self.product_identifier_local is None:
                            self.welformed_data = False
                    case Oid.MEDIA_FORMAT_OTHER:
                        if self.media_format_other is None:
                            self.welformed_data = False
                    case Oid.SUPPLY_CHAIN_STAGE:
                        if self.supply_chain_stage is None:
                            self.welformed_data = False
                    case Oid.SUPPLIER_INVOICE_NUMBER:
                        if self.supplier_invoice_number is None:
                            self.welformed_data = False
                    case Oid.ALTERNATIVE_ITEM_IDENTIFIER:
                        if self.alternative_item_identifier is None:
                            self.welformed_data = False
                    case Oid.ALTERNATIVE_OWNER_LIBRARY_IDENTIFIER:
                        if self.alternative_owner_library_identifier is None:
                            self.welformed_data = False
                    case Oid.SUBSIDIARY_OF_AN_OWNER_LIBRARY:
                        if self.subsidiary_of_an_owner_library is None:
                            self.welformed_data = False
                    case Oid.ALTERNATIVE_ILL_BORROWING_INSTITUTION:
                        if self.alternative_ill_borrowing_institution is None:
                            self.welformed_data = False
                    case Oid.LOCAL_DATA_C:
                        if self.local_data_c is None:
                            self.welformed_data = False
        """
