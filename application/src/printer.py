"""
Printer module for Signum labeller application
Contains printer-specific classes, constants, and utility functions
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional

import sentry_sdk
from brother_ql.backends.helpers import discover, send
from brother_ql.conversion import convert
from brother_ql.raster import BrotherQLRaster
from PIL import Image, ImageDraw, ImageFont


class PrinterState(Enum):
    """
    Label printer states.
    """

    NO_PRINTER_CONNECTED = 0
    PRINTER_CONNECTED = 1


@dataclass
class PrintResult:
    """
    Result structure for printer operations
    """

    state: PrinterState
    device: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


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
    create_signum Creates a signum image for printing

    :param classification: the classification (in YKL)
    :param shelfmark: three letter word for alphabetical sorting
    :param font_path: path to the font to use
    :param minimum_font_height: minimum font size to use (text will use all the space it can get)
    :param width: width of the signum in pixels. Note that this has to correspond to brother-ql continous roll widths
    :param height: height of the signum in pixels. The minimum value is 42 which corresponds to 9mm.
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


class Printer:
    """
    Printer class that handles all printer-specific operations and state management
    """

    def __init__(self, model: str, label: str):
        self.state: PrinterState = PrinterState.NO_PRINTER_CONNECTED
        self.device: Optional[Dict[str, Any]] = None
        self.model = model
        self.label = label

    def discover_printer(self) -> PrintResult:
        """
        Discovers available Brother QL printers

        :return: PrintResult with current state and device info
        """
        try:
            devices = discover(backend_identifier="pyusb")
            if not devices:
                self.state = PrinterState.NO_PRINTER_CONNECTED
                self.device = None
            else:
                self.state = PrinterState.PRINTER_CONNECTED
                self.device = devices[0]

            return PrintResult(state=self.state, device=self.device)

        except Exception as e:
            sentry_sdk.capture_exception(error=e)
            self.state = PrinterState.NO_PRINTER_CONNECTED
            self.device = None
            return PrintResult(
                state=self.state, device=self.device, error=f"Printer discovery failed: {str(e)}"
            )

    def print_signum(self, classification: str, shelfmark: str, material_code: str = None) -> bool:
        """
        Creates and prints a signum label

        :param classification: the classification text
        :param shelfmark: the shelfmark text
        :param material_code: optional material code to determine label size
        :return: True if printing succeeded, False otherwise
        """
        if self.state != PrinterState.PRINTER_CONNECTED or not self.device:
            return False

        try:
            # Print different size signum sticker for CDs
            if material_code == "3":
                signum_height = 40
                minimum_font_height = 32
            else:
                signum_height = 42
                minimum_font_height = 32

            image = create_signum(
                classification=classification,
                shelfmark=shelfmark,
                font_path="assets/arial.ttf",
                minimum_font_height=minimum_font_height,
                width=413,
                height=signum_height,
            )
            qlr = BrotherQLRaster(self.device.get("model", self.model))
            qlr.exception_on_warning = False
            instructions = convert(
                qlr=qlr,
                images=[image],
                label=self.label,
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
                printer_identifier=self.device["identifier"],
                backend_identifier=self.device.get("backend", "pyusb"),
                blocking=False,
            )

            return True

        except Exception as e:
            print(e)
            sentry_sdk.capture_exception(error=e)
            return False
