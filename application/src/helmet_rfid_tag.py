iso_iec_latch_shift_values = ["Latch upper", "Shift upper", "Latch lower", "Shift lower", "Latch numeric", "Shift numeric"]

iso_iec_4bit_numeric_encoding = {
    "0000": "0", "0001": "1", "0010": "2", "0011": "3",
    "0100": "4", "0101": "5", "0110": "6", "0111": "7",
    "1000": "8", "1001": "9", "1010": "-", "1011": ":",
    "1100": "Latch upper", "1101": "Shift upper", "1110": "Latch lower", "1111": "Shift lower"
}

iso_iec_5bit_uppercase_encoding_dict = {
    "00000": "-", "00001": "A", "00010": "B", "00011": "C",
    "00100": "D", "00101": "E", "00110": "F", "00111": "G",
    "01000": "H", "01001": "I", "01010": "J", "01011": "K",
    "01100": "L", "01101": "M", "01110": "N", "01111": "O",
    "10000": "P", "10001": "Q", "10010": "R", "10011": "S",
    "10100": "T", "10101": "U", "10110": "V", "10111": "W",
    "11000": "X", "11001": "Y", "11010": "Z", "11011": ":",
    "11100": "Latch lower", "11101": "Shift lower", "11110": "Latch numeric", "11111": "Shift numeric"
}

iso_iec_5bit_lowercase_encoding_dict = {
    "00000": "-", "00001": "a", "00010": "b", "00011": "c",
    "00100": "d", "00101": "e", "00110": "f", "00111": "g",
    "01000": "h", "01001": "i", "01010": "j", "01011": "k",
    "01100": "l", "01101": "m", "01110": "n", "01111": "o",
    "10000": "p", "10001": "q", "10010": "r", "10011": "s",
    "10100": "t", "10101": "u", "10110": "v", "10111": "w",
    "11000": "x", "11001": "y", "11010": "z", "11011": "/",
    "11100": "Latch upper", "11101": "Shift upper", "11110": "Latch numeric", "11111": "Shift numeric"
}

iso_iec_6bit_dict = {
    "000000": "@", "000001": "A", "000010": "B", "000011": "C",
    "000100": "D", "000101": "E", "000110": "F", "000111": "G",
    "001000": "H", "001001": "I", "001010": "J", "001011": "K",
    "001100": "L", "001101": "M", "001110": "N", "001111": "O",
    "010000": "P", "010001": "Q", "010010": "R", "010011": "S",
    "010100": "T", "010101": "U", "010110": "V", "010111": "W",
    "011000": "X", "011001": "Y", "011010": "Z", "011011": "[",
    "011100": "\\", "011101": "]", "011110": "^", "011111": "_",
    "100000": " ", "100001": "EOT", "100010": "Reserved", "100011": "FS",
    "100100": "US", "100101": "Reserved", "100110": "Reserved", "100111": "Reserved",
    "101000": "(", "101001": ")", "101010": "*", "101011": "+",
    "101100": ",", "101101": "-", "101110": ".", "101111": "/",
    "110000": "0", "110001": "1", "110010": "2", "110011": "3",
    "110100": "4", "110101": "5", "110110": "6", "110111": "7",
    "111000": "8", "111001": "9", "111010": ":", "111011": ";",
    "111100": "<", "111101": "=", "111110": ">", "111111": "?"
}

content_parameter_map = {
    "0" : {
        "class": "Acquisition item",
        "sub-qualifiers": {
            "0": "Acquisition item, unspecified",
            "1": "Acquisition item, for automated process",
            "2": "Acquisition item, for manual process",
            "3456789ABCDEF": "For future use within the class"
        }
    },
    "1" : {
        "class": "Item for circulation",
        "sub-qualifiers": {
            "0": "Circulating item, unspecified",
            "1": "Circulating item, for automatic sorting",
            "2": "Circulating item, not for automatic sorting",
            "3": "Circulating item, not for issue while offline",
            "4": "Circulating item, not for return while offline",
            "5": "Circulating item, not for issue or return while offline",
            "6789ABCDEF": "For future use within the class"
        }
    },
    "2" : {
        "class": "Item Not For Circulation",
        "sub-qualifiers": {
            "0": "Non-circulating item, unspecified",
            "1234567890ABCDEF": "For future use within the class"
        }
    },
    "3" : {
        "class": "For Local Use",
        "sub-qualifiers": {
            "0": "For local use, unspecified sub-class",
            "1234567890ABCDEF": "For future use within the class"
        }
    },
    "4" : {
        "class": "For Local Use",
        "sub-qualifiers": {
            "0": "For local use, unspecified sub-class",
            "1234567890ABCDEF": "For future use within the class"
        }
    },
    "5" : {
        "class": "For Future Use",
        "sub-qualifiers": {
            "0": "For future use, unspecified sub-class",
            "1234567890ABCDEF": "For future use within the class"
        }
    },
    "6" : {
        "class": "No information about usage on the tag",
        "sub-qualifiers": {
            "0": "If the type of usage data element is locked, with a type of usage which can change over time, it should be encoded as a 6.",
            "1234567890ABCDEF": "Not to be used"
        }
    },
    "7" : {
        "class": "Discarded item",
        "sub-qualifiers": {
            "0": "Discarded item, unspecified",
            "1": "Discarded item, for sale",
            "2": "Discarded item, sold",
            "3": "Discarded item, for disposal",
            "456789ABCDEF": "For future use within the class"
        }
    },
    "8" : {
        "class": "Patron card",
        "sub-qualifiers": {
            "0": "Patron card, unspecified",
            "1": "Patron card, adult borrower",
            "2": "Patron card, young adult borrower",
            "3": "Patron card, standard child borrower",
            "456789ABCDEF": "For future use within the class"
        }
    },
    "9" : {
        "class": "Library equipment",
        "sub-qualifiers": {
            "0": "Library equipment, unspecified",
            "1": "Personal computer",
            "2": "Video projector",
            "3": "Overhead projector",
            "4": "Whiteboard",
            "56789ABCDEF": "For future use within the class"
        }
    },
    "A" : {
        "class": "For Future Use",
        "sub-qualifiers": {
            "0": "For future use, unspecified sub-class",
            "1234567890ABCDEF": "For future use within the class"
        }
    },
    "B" : {
        "class": "For Future Use",
        "sub-qualifiers": {
            "0": "For future use, unspecified sub-class",
            "1234567890ABCDEF": "For future use within the class"
        }
    },
    "C" : {
        "class": "For Future Use",
        "sub-qualifiers": {
            "0": "For future use, unspecified sub-class",
            "1234567890ABCDEF": "For future use within the class"
        }
    },
    "D" : {
        "class": "For Future Use",
        "sub-qualifiers": {
            "0": "For future use, unspecified sub-class",
            "1234567890ABCDEF": "For future use within the class"
        }
    },
    "E" :{
        "class": "For Future Use",
        "sub-qualifiers": {
            "0": "For future use, unspecified sub-class",
            "1234567890ABCDEF": "For future use within the class"
        }
    },
    "F" : {
        "class": "For Future Use",
        "sub-qualifiers": {
            "0": "For future use, unspecified sub-class",
            "1234567890ABCDEF": "For future use within the class"
        }
    }
}

def decode_iso_iec_4bit(binary_string, starting_dict):
    # FIXME: implement
    return ""

def decode_iso_iec_4bit_5bit(binary_string, starting_dict):
    result = []
    shift = False

    bs_to_process = binary_string
    active_dict = starting_dict
    latch_dict = starting_dict
    shift_dict = starting_dict

    while len(bs_to_process) > 3:
        if shift:
            active_dict = shift_dict
        else:
            active_dict = latch_dict

        shift = False

        for key in active_dict:
            if bs_to_process[0:len(key)] == key :
                if active_dict[key] not in iso_iec_latch_shift_values:
                    result.append(active_dict[key])
                elif("Latch" in active_dict[key]):
                    if "upper" in active_dict[key]:
                        latch_dict = iso_iec_5bit_uppercase_encoding_dict
                    elif "lower" in active_dict[key]:
                        latch_dict = iso_iec_5bit_lowercase_encoding_dict
                    else:
                        latch_dict = iso_iec_4bit_numeric_encoding
                elif("Shift" in active_dict[key]):
                    if "upper" in active_dict[key]:
                        shift_dict = iso_iec_5bit_uppercase_encoding_dict
                    elif "lower" in active_dict[key]:
                        shift_dict = iso_iec_5bit_lowercase_encoding_dict
                    else:
                        shift_dict = iso_iec_4bit_numeric_encoding
                    shift = True
                bs_to_process = bs_to_process[len(key):]

    return "".join(result)
            
def decode_iso_iec_6bit(binary_string, starting_dict):
    # FIXME: implement
    return ""

def decode_iso_iec_7bit(binary_string, starting_dict):
    # FIXME: implement
    return ""

def decode_iso_iec_8859_1(binary_string, starting_dict):
    # FIXME: implement
    return ""

def decode_utf_8_iso_iec_10646_external_compaction(binary_string, starting_dict):
    # FIXME: implement
    return ""

    
class HelmetRfidTag():

    welformed_data = False

    primary_item_identifier = None # OID 1
    content_parameter = None # OID 2
    owner_library_isil = None # OID 3
    set_information = None # OID 4
    type_of_usage = None # OID 5
    shelf_location = None # OID 6
    onix_media_format = None # OID 7
    marc_media_format = None # OID 8
    supplier_identifier = None # OID 9
    order_number = None # OID 10
    ill_borrowing_institution_isil = None # OID 11
    ill_borrowing_transaction_number = None # OID 12
    gs1_product_identifier = None # OID 13
    alternative_unique_item_identifier = None # OID 14
    local_data_a = None # OID 15
    local_data_b = None # OID 16
    title = None # OID 17
    product_identifier_local = None # OID 18
    media_format_other = None # OID 19
    supply_chain_stage = None # OID 20
    supplier_invoice_number = None # OID 21
    alternative_item_identifier = None # OID 22
    alternative_owner_library_identifier = None # OID 23
    subsidiary_of_an_owner_library = None # OID 24
    alternative_ill_borrowing_institution = None # OID 25
    local_data_c = None # OID 26

    def __init__(self, data_bytes):
        if data_bytes is not None:
             self.parse_data(data_bytes)

    def decode(self, encoding, data, oid):
        match (encoding, oid):
            case (0, 2): # Application specific, for oid 2 (content parameter), returns expected oids
                expected_oids = []
                relative_oids = [3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29,30,31,32]
                for index, bit in enumerate(data):
                    if bit == "1":
                        expected_oids.append(relative_oids[index])
                return expected_oids
            case (0, 3): # Application specific, for oid 3 (ISIL)
                return decode_iso_iec_4bit_5bit(data, iso_iec_5bit_uppercase_encoding_dict)
            case (0, 5): # Application specific, for oid 5 (type of usage)
                try:
                    class_qualifier = format(int(data[0:4],2), "X")
                    sub_qualifier = format(int(data[4:8],2), "X")
                    cls = content_parameter_map[class_qualifier]["class"]
                    sub_quals = content_parameter_map[class_qualifier]["sub-qualifiers"]
                    for key in sub_quals:
                        if sub_qualifier in key:
                            return (cls, sub_quals[key])
                except:
                    return None
                return None
            case (0, _): # Application specific, oid not handled
                return f"unhandled app specific encoding, oid: {oid}, data: {data}"            
            case (1, _): # Unsigned big-endian integer
                return int.from_bytes(
                        int(data, 2).to_bytes((len(data) + 7) // 8),
                        byteorder='big',
                        signed=False
                    )
            case (2, _): # Numeric string 0-9
                return data 
            case (3, _): # 5-bit code, Uppercase alphabetic
                return data 
            case (4, _): # 6-bit code, Uppercase, numeric, etc.
                return data 
            case (5, _): # 7-bit code, US ASCII
                return data 
            case (6, _): # Octet string, Unaltered 8 bit (default = ISO/IEC 8859-1)
                return data 
            case (7, _): # UTF-8 string, External compaction to ISO/IEC 10646
                return data 
            case (8, _): # Unknown compaction
                return f"unknown encoding: {encoding}, data: {data}" 
            case (_, _): # Unknown compaction
                return f"unknown encoding: {encoding}, data: {data}"

    def parse_data(self, data_bytes):
        bin_text = ''.join(format(byte, '08b') for byte in data_bytes)                 
        length = 0
        prev_length = 0
        try:
            while len(bin_text) > 0 and len(bin_text) != prev_length:
                precursor = bin_text[0]
                encoding = int(bin_text[1: 4], 2)
                oid = int(bin_text[4: 8], 2)
                try:
                    length = int(bin_text[8: 16],2)
                except:
                    length = 0
                data = bin_text[16: 16 + length * 8]
                value = self.decode(encoding=encoding, data=data, oid=oid)
                match oid:
                    case 1: self.primary_item_identifier = value
                    case 2: self.content_parameter = value
                    case 3: self.owner_library_isil = value
                    case 4: self.set_information = value
                    case 5: self.type_of_usage = value
                    case 6: self.shelf_location = value
                    case 7: self.onix_media_format = value
                    case 8: self.marc_media_format = value
                    case 9: self.supplier_identifier = value
                    case 10: self.order_number = value
                    case 11: self.ill_borrowing_institution_isil = value
                    case 12: self.ill_borrowing_transaction_number = value
                    case 13: self.gs1_product_identifier = value
                    case 14: self.alternative_unique_item_identifier = value
                    case 15: self.local_data_a = value
                    case 16: self.local_data_b = value
                    case 17: self.title = value
                    case 18: self.product_identifier_local = value
                    case 19: self.media_format_other = value
                    case 20: self.supply_chain_stage = value
                    case 21: self.supplier_invoice_number = value
                    case 22: self.alternative_item_identifier = value
                    case 23: self.alternative_owner_library_identifier = value
                    case 24: self.subsidiary_of_an_owner_library = value
                    case 25: self.alternative_ill_borrowing_institution = value
                    case 26: self.local_data_c = value
                prev_length = len(bin_text)
                bin_text = bin_text[(16 + length * 8):]
        except Exception as e:
            self.welformed_data = False
            pass

        self.welformed_data = True

        if(self.primary_item_identifier is None or self.primary_item_identifier == ""): self.welformed_data = False
        if(self.content_parameter is None): self.welformed_data = False
        if(self.content_parameter is not None):
            for oid in self.content_parameter:
                match oid:
                    case 3:
                        if(self.owner_library_isil is None): self.welformed_data = False
                        if(self.owner_library_isil not in ["FI-He","FI-Em","FI-Vantaa","FI-Kauni"]): self.welformed_data = False
                    case 4:
                        if(self.set_information is None): self.welformed_data = False
                    case 5:
                        if(self.type_of_usage is None): self.welformed_data = False 
                    case 6:
                        if(self.shelf_location is None): self.welformed_data = False
                    case 7:
                        if(self.onix_media_format is None): self.welformed_data = False
                    case 8:
                        if(self.marc_media_format is None): self.welformed_data = False
                    case 9:
                        if(self.supplier_identifier is None): self.welformed_data = False
                    case 10:
                        if(self.order_number is None): self.welformed_data = False
                    case 11:
                        if(self.ill_borrowing_institution_isil  is None): self.welformed_data = False
                    case 12:
                        if(self.ill_borrowing_transaction_number is None): self.welformed_data = False
                    case 13:
                        if(self.gs1_product_identifier is None): self.welformed_data = False
                    case 14:
                        if(self.alternative_unique_item_identifier is None): self.welformed_data = False
                    case 15:
                        if(self.local_data_a is None): self.welformed_data = False
                    case 16:
                        if(self.local_data_b is None): self.welformed_data = False
                    case 17:
                        if(self.title is None): self.welformed_data = False
                    case 18:
                        if(self.product_identifier_local is None): self.welformed_data = False
                    case 19:
                        if(self.media_format_other is None): self.welformed_data = False
                    case 20:
                        if(self.supply_chain_stage is None): self.welformed_data = False
                    case 21:
                        if(self.supplier_invoice_number is None): self.welformed_data = False
                    case 22:
                        if(self.alternative_item_identifier is None): self.welformed_data = False
                    case 23:
                        if(self.alternative_owner_library_identifier is None): self.welformed_data = False
                    case 24:
                        if(self.subsidiary_of_an_owner_library is None): self.welformed_data = False
                    case 25:
                        if(self.alternative_ill_borrowing_institution is None): self.welformed_data = False
                    case 26:
                        if(self.local_data_c is None): self.welformed_data = False
