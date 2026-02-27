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
from brother_ql.labels import ALL_LABELS
from brother_ql.raster import BrotherQLRaster
from PIL import Image, ImageDraw, ImageFont

LABEL_PRINTABLE_WIDTHS = {label.identifier: label.dots_printable[0] for label in ALL_LABELS}


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


def create_signum(
    classification,
    shelfmark,
    font_path,
    minimum_font_height,
    width,
    height,
    spacing=10,
    stroke_width=0,
):
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

    # Prevent overlap: shrink both fonts by one point at a time until the combined
    # text width fits within the label width.
    while (
        draw.textlength(classification, font=classification_font)
        + spacing
        + draw.textlength(shelfmark, font=shelfmark_font)
    ) > width:
        new_size = classification_font.size - 1
        if new_size < minimum_font_height:
            break
        classification_font = ImageFont.truetype(font_path, new_size)
        classification_bbox = classification_font.getbbox(classification)
        classification_height = classification_bbox[3] - classification_bbox[1]
        shelfmark_font = ImageFont.truetype(font_path, new_size)
        shelfmark_bbox = shelfmark_font.getbbox(shelfmark)
        shelfmark_height = shelfmark_bbox[3] - shelfmark_bbox[1]

    shelfmark_position = (
        width - draw.textlength(shelfmark, font=shelfmark_font),
        (im_height - shelfmark_height) / 2 - shelfmark_bbox[1],
    )
    classification_position = (0, (im_height - classification_height) / 2 - classification_bbox[1])

    draw.text(
        classification_position,
        classification,
        fill="black",
        font=classification_font,
        stroke_width=stroke_width,
        stroke_fill="black",
    )
    draw.text(
        shelfmark_position,
        shelfmark,
        fill="black",
        font=shelfmark_font,
        stroke_width=stroke_width,
        stroke_fill="black",
    )

    return image


class Printer:
    """
    Printer class that handles all printer-specific operations and state management
    """

    def __init__(
        self,
        model: str,
        label: str,
        red: bool,
        dpi_600: bool = False,
        hq: bool = False,
        dither: bool = False,
        compress: bool = True,
        signum_height: int = 42,
        signum_height_cd: int = 40,
        minimum_font_height: int = 32,
        signum_spacing: int = 10,
        font_path: str = "assets/arialn.ttf",
        font_stroke_width: int = 0,
    ):
        self.state: PrinterState = PrinterState.NO_PRINTER_CONNECTED
        self.device: Optional[Dict[str, Any]] = None
        self.model = model
        self.label = label
        self.red = red
        self.dpi_600 = dpi_600
        self.hq = hq
        self.dither = dither
        self.compress = compress
        self.signum_height = signum_height
        self.signum_height_cd = signum_height_cd
        self.minimum_font_height = minimum_font_height
        self.signum_spacing = signum_spacing
        self.font_path = font_path
        self.font_stroke_width = font_stroke_width

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
                signum_height = self.signum_height_cd
            else:
                signum_height = self.signum_height

            dpi_scale = 2 if self.dpi_600 else 1
            image = create_signum(
                classification="88.88888",  # classification,
                shelfmark="ÄÖÅ",  # shelfmark,
                font_path=self.font_path,
                minimum_font_height=self.minimum_font_height * dpi_scale,
                width=LABEL_PRINTABLE_WIDTHS.get(self.label, 413) * dpi_scale,
                height=signum_height * dpi_scale,
                spacing=self.signum_spacing * dpi_scale,
                stroke_width=self.font_stroke_width * dpi_scale,
            )
            qlr = BrotherQLRaster(self.device.get("model", self.model))
            qlr.exception_on_warning = False
            print(
                f"model: {self.model} , label: {self.label} , red: {self.red} , dpi_600: {self.dpi_600} , hq: {self.hq}"
            )
            instructions = convert(
                qlr=qlr,
                images=[image],
                label=self.label,
                rotate="auto",
                threshold=70.0,
                dither=self.dither,
                compress=self.compress,
                red=self.red,
                dpi_600=self.dpi_600,
                hq=self.hq,
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
