"""
Printer module for Signum labeller application.

Defines a backend-strategy abstraction (PrinterBackend) with two implementations:
  * BrotherQLBackend - drives Brother QL series printers via brother_ql.
  * BrotherPTBackend - drives Brother PT series (e.g. PT-P710BT) via brother_pt.

The Printer orchestrator picks a backend based on the `printer.backend` config key
(`ql` or `pt`) and delegates discovery and printing to it.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional, Tuple

import sentry_sdk
from brother_ql.backends.helpers import discover as ql_discover
from brother_ql.backends.helpers import send as ql_send
from brother_ql.conversion import convert as ql_convert
from brother_ql.labels import ALL_LABELS
from brother_ql.raster import BrotherQLRaster
from PIL import Image, ImageDraw, ImageFont

LABEL_PRINTABLE_WIDTHS = {label.identifier: label.dots_printable[0] for label in ALL_LABELS}

# Step size used when growing/shrinking font sizes during text fitting.
# Fractional (vs the previous 1.0) so width-shrink doesn't drop height by a
# whole point per step, which used to leave a 1-2 px white margin on top and
# bottom of long labels after vertical centering.
FONT_SIZE_STEP = 0.1


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
    Find the largest font size whose rendered text fits within target_height.

    Uses FONT_SIZE_STEP (0.1 pt) increments so the height match is precise.
    Post-condition: bbox height <= target_height (no overshoot).

    :param text: the text to be fitted
    :param initial_size: starting font size in pt; may be int or float
    :param font_path: path to the font to use
    :param target_height: target height in pixels
    :return: (ImageFont font, bbox tuple, height float) for the largest fitting size
    """
    font_size = float(initial_size)
    font = ImageFont.truetype(font_path, font_size)
    bbox = font.getbbox(text)
    height = bbox[3] - bbox[1]

    if height > target_height:
        # Defensive: shrink if the caller passed an oversized initial_size.
        while height > target_height and font_size > FONT_SIZE_STEP:
            font_size -= FONT_SIZE_STEP
            font = ImageFont.truetype(font_path, font_size)
            bbox = font.getbbox(text)
            height = bbox[3] - bbox[1]
    else:
        # Grow only while the next step would still fit. Never overshoot.
        while True:
            next_size = font_size + FONT_SIZE_STEP
            next_font = ImageFont.truetype(font_path, next_size)
            next_bbox = next_font.getbbox(text)
            next_height = next_bbox[3] - next_bbox[1]
            if next_height > target_height:
                break
            font_size, font, bbox, height = next_size, next_font, next_bbox, next_height

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
    cd_wrap_expansion=True,
    auto_width=False,
):
    """
    create_signum Creates a signum image for printing

    :param classification: the classification (in YKL)
    :param shelfmark: three letter word for alphabetical sorting
    :param font_path: path to the font to use
    :param minimum_font_height: minimum font size to use (text will use all the space it can get)
    :param width: width of the signum in pixels (ignored when auto_width=True). For QL: must match
        the brother-ql continuous-roll printable width. For PT (auto_width=True) the image grows
        to fit the natural text width instead.
    :param height: height of the signum in pixels. The minimum value is 42 which corresponds to 9mm.
        Values less than that are considered to be CD case signums which will result in additional blank space added.
    :param cd_wrap_expansion: if True (default, for QL die-cut/continuous label paper), heights below 42 px get 5x
        vertical padding so the printed label can be wrapped around a CD jewel case. PT tape backends pass False
        because tape is cut to length and wrapping does not apply.
    :param auto_width: if True, image width is computed from the rendered text widths at full target
        height (no width-shrink, no horizontal truncation). Used by PT-series backends where tape is
        continuous and label length can vary per print.
    :return: Image the signum image
    """

    # Standard label height is 42 pixels (9 mm) which is also the minumum height for brother-ql cutting unit.
    # Signums labels with maximum label text of 6mm height are used in CD jewel cases and digipacks.
    # CD signum labels are printed with extra blank space above and below the signum.
    # The label is wrapped around the case. This ensures that the label adhesive works properly.
    im_height = height
    if cd_wrap_expansion and height < 42:
        im_height = height * 5

    # Fit each font to the target height first so we can measure natural text
    # widths before deciding the final image width.
    classification_font, classification_bbox, classification_height = get_font_size_for_text(
        classification, minimum_font_height, font_path, height
    )
    shelfmark_font, shelfmark_bbox, shelfmark_height = get_font_size_for_text(
        shelfmark, minimum_font_height, font_path, height
    )

    classification_w = classification_font.getlength(classification)
    shelfmark_w = shelfmark_font.getlength(shelfmark)

    if auto_width:
        # Variable-width label: image grows to fit the natural text width at
        # full target height. No shrink, no truncation. Used by PT tape
        # backends where tape is continuous. The passed `width` is treated as
        # a minimum floor so configured signum_length_pt / signum_length_cd_pt
        # values give short labels a consistent baseline length; the
        # classification stays left-anchored and the shelfmark right-anchored,
        # so extra space when width > natural opens up between the two texts.
        eff_spacing = spacing if (classification and shelfmark) else 0
        natural_width = int(classification_w + eff_spacing + shelfmark_w)
        width = max(natural_width, width, 1)
    else:
        # Fixed-width label: shrink both fonts by FONT_SIZE_STEP (0.1 pt) at a
        # time until the combined text fits the label width. Fractional steps
        # keep the resulting height very close to target so vertical centering
        # doesn't leave a visible white margin on top and bottom.
        while (classification_w + spacing + shelfmark_w) > width:
            new_size = classification_font.size - FONT_SIZE_STEP
            if new_size < minimum_font_height:
                break
            classification_font = ImageFont.truetype(font_path, new_size)
            classification_bbox = classification_font.getbbox(classification)
            classification_height = classification_bbox[3] - classification_bbox[1]
            classification_w = classification_font.getlength(classification)
            shelfmark_font = ImageFont.truetype(font_path, new_size)
            shelfmark_bbox = shelfmark_font.getbbox(shelfmark)
            shelfmark_height = shelfmark_bbox[3] - shelfmark_bbox[1]
            shelfmark_w = shelfmark_font.getlength(shelfmark)

    image = Image.new("RGB", (width, im_height), color="white")
    draw = ImageDraw.Draw(image)

    shelfmark_position = (
        width - shelfmark_w,
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


class PrinterBackend(ABC):
    """
    Strategy interface for a printer backend. Each implementation wraps a
    library/protocol for a specific Brother printer family.
    """

    # Whether create_signum should apply the QL CD-wrap 5x expansion for
    # heights below 42 px. Tape backends override to False since tape is cut
    # to length rather than wrapped around a case.
    cd_wrap_expansion: bool = True

    # Whether create_signum should size the image to fit the rendered text
    # rather than honour the configured width. Continuous-tape backends (PT)
    # override to True so labels grow to fit long classifications without
    # shrinking the font. QL backends keep False — their label widths are
    # fixed by the roll geometry.
    auto_width: bool = False

    @abstractmethod
    def discover(self) -> PrintResult:
        """
        Cheap, frequently-called USB enumeration. Must not open / claim the
        device or detach kernel drivers; the orchestrator polls this every
        ~100 ms via the Qt timer in the main reader loop.
        """

    @abstractmethod
    def print_image(self, image: Image.Image) -> bool:
        """
        Print a PIL image. Returns True on success, False on failure.
        Implementations should capture exceptions to Sentry and recover so the
        next call can succeed (e.g. by reopening the device).
        """

    @abstractmethod
    def signum_canvas(self, material_code: Optional[str]) -> Tuple[int, int, int, int, int]:
        """
        Returns the geometry to feed into create_signum:
        (width_px, height_px, minimum_font_px, spacing_px, stroke_width_px).

        The dimensions follow the create_signum convention: `width` is the
        text-reading direction, `height` is the perpendicular dimension.
        """


class BrotherQLBackend(PrinterBackend):
    """
    Backend for Brother QL series (e.g. QL-810W) using the brother_ql library.
    """

    def __init__(
        self,
        model: str,
        label: str,
        red: bool,
        dpi_600: bool,
        hq: bool,
        dither: bool,
        compress: bool,
        signum_height: int,
        signum_height_cd: int,
        minimum_font_height: int,
        signum_spacing: int,
        font_stroke_width: int,
    ):
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
        self.font_stroke_width = font_stroke_width
        self._device: Optional[Dict[str, Any]] = None

    def discover(self) -> PrintResult:
        try:
            devices = ql_discover(backend_identifier="pyusb")
            if not devices:
                self._device = None
                return PrintResult(state=PrinterState.NO_PRINTER_CONNECTED)
            self._device = devices[0]
            return PrintResult(state=PrinterState.PRINTER_CONNECTED, device=self._device)
        except Exception as e:
            sentry_sdk.capture_exception(error=e)
            self._device = None
            return PrintResult(
                state=PrinterState.NO_PRINTER_CONNECTED,
                error=f"Printer discovery failed: {str(e)}",
            )

    def print_image(self, image: Image.Image) -> bool:
        if not self._device:
            return False
        try:
            qlr = BrotherQLRaster(self._device.get("model", self.model))
            qlr.exception_on_warning = False
            print(
                f"model: {self.model} , label: {self.label} , red: {self.red} , "
                f"dpi_600: {self.dpi_600} , hq: {self.hq}"
            )
            instructions = ql_convert(
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
            ql_send(
                instructions=instructions,
                printer_identifier=self._device["identifier"],
                backend_identifier=self._device.get("backend", "pyusb"),
                blocking=False,
            )
            return True
        except Exception as e:
            print(e)
            sentry_sdk.capture_exception(error=e)
            return False

    def signum_canvas(self, material_code: Optional[str]) -> Tuple[int, int, int, int, int]:
        scale = 2 if self.dpi_600 else 1
        height = self.signum_height_cd if material_code == "3" else self.signum_height
        return (
            LABEL_PRINTABLE_WIDTHS.get(self.label, 413) * scale,
            height * scale,
            self.minimum_font_height * scale,
            self.signum_spacing * scale,
            self.font_stroke_width * scale,
        )


class BrotherPTBackend(PrinterBackend):
    """
    Backend for Brother PT series (e.g. PT-P710BT) using the brother_pt library.

    PT printers run at 180 dpi and auto-detect the inserted tape width. The
    `BrotherPt` USB handle is opened lazily on first print (and on first canvas
    query) so that the 100 ms reader loop can poll discover() cheaply without
    repeatedly claiming the USB device.
    """

    cd_wrap_expansion = False
    auto_width = True

    # Used as a fallback when we have to guess the tape width before the
    # printer has been opened (e.g. very first call). 12 mm is the most common
    # P-touch tape size.
    _FALLBACK_TAPE_WIDTH_MM = 12

    # Valid cut_mode values (case-insensitive). See class docstring for the
    # protocol mapping each value applies on the printer.
    #
    #   auto  - Mode.AUTO_CUT + \x1A: cut at start (clears leader scrap)
    #           and at end (clean trailing edge). Two pieces per print
    #           (~25 mm scrap + clean content label). Default; matches QL.
    #   chain - Mode(0)       + \x1A: cut at end only. One piece per print
    #           but with a ~25 mm blank prefix from the cutter offset.
    #   none  - Mode(0)       + \x0C: no cuts at all. Tape accumulates on
    #           a single strip; user manually cuts.
    CUT_MODES = ("auto", "chain", "none")

    def __init__(
        self,
        serial: Optional[str],
        margin_px: int,
        signum_length_pt: int,
        signum_length_cd_pt: int,
        minimum_font_height_pt: int,
        signum_spacing_pt: int,
        font_stroke_width_pt: int,
        cut_mode: str = "auto",
    ):
        # Lazy import from the vendored copy of treideme/brother_pt; deferring
        # the import keeps QL-only deployments resilient if anything in the
        # vendored stack (e.g. PIL/usb shim) misbehaves on a particular host.
        from vendor.brother_pt import BrotherPt, find_printers
        from vendor.brother_pt.cmd import (
            MediaWidthToTapeMargin,
            Mode,
            print_with_feeding,
            print_without_feeding,
        )

        self._BrotherPt = BrotherPt
        self._find_printers = find_printers
        self._MediaWidthToTapeMargin = MediaWidthToTapeMargin
        self._Mode = Mode
        self._print_with_feeding = print_with_feeding
        self._print_without_feeding = print_without_feeding

        self.serial = serial or None
        self.margin_px = margin_px
        self.signum_length_pt = signum_length_pt
        self.signum_length_cd_pt = signum_length_cd_pt
        self.minimum_font_height_pt = minimum_font_height_pt
        self.signum_spacing_pt = signum_spacing_pt
        self.font_stroke_width_pt = font_stroke_width_pt

        normalized = (cut_mode or "auto").strip().lower()
        self.cut_mode = normalized if normalized in self.CUT_MODES else "auto"

        self._pt: Optional[Any] = None
        self._printable_width_px: Optional[int] = None

    def _drop(self):
        self._pt = None
        self._printable_width_px = None

    def discover(self) -> PrintResult:
        try:
            printers = self._find_printers(serial=self.serial)
            if not printers:
                self._drop()
                return PrintResult(state=PrinterState.NO_PRINTER_CONNECTED)
            return PrintResult(
                state=PrinterState.PRINTER_CONNECTED,
                device={
                    "model": "PT-P710BT",
                    "backend": "pyusb",
                    "identifier": self.serial or "auto",
                },
            )
        except Exception as e:
            sentry_sdk.capture_exception(error=e)
            self._drop()
            return PrintResult(
                state=PrinterState.NO_PRINTER_CONNECTED,
                error=f"Printer discovery failed: {str(e)}",
            )

    def _ensure_open(self) -> None:
        if self._pt is not None:
            return
        # Upstream BrotherPt's `serial` param is mistyped as `str` rather than
        # `Optional[str]`, but `find_printers(None)` is the documented "any
        # device" path. Suppress here rather than patching vendored source.
        pt = self._BrotherPt(serial=self.serial)  # type: ignore[arg-type]
        pt.update_status()
        # Map cut_mode onto the two protocol attributes the vendored
        # print_data reads via getattr:
        #   auto    -> Mode.AUTO_CUT + \x1A: cut before + cut after (two pieces).
        #   chain   -> Mode(0)       + \x1A: cut after only (leader-included label).
        #   none    -> Mode(0)       + \x0C: no cuts at all (batch on a strip).
        if self.cut_mode == "auto":
            pt._mode = self._Mode.AUTO_CUT  # type: ignore[attr-defined]
            pt._final_cmd = self._print_with_feeding  # type: ignore[attr-defined]
        elif self.cut_mode == "chain":
            pt._mode = self._Mode(0)  # type: ignore[attr-defined]
            pt._final_cmd = self._print_with_feeding  # type: ignore[attr-defined]
        else:  # "none"
            pt._mode = self._Mode(0)  # type: ignore[attr-defined]
            pt._final_cmd = self._print_without_feeding  # type: ignore[attr-defined]
        self._pt = pt
        self._printable_width_px = self._MediaWidthToTapeMargin.to_print_width(pt.media_width)

    def print_image(self, image: Image.Image) -> bool:
        try:
            self._ensure_open()
            assert self._pt is not None
            self._pt.print_image(image, margin_px=self.margin_px)
            return True
        except Exception as e:
            print(e)
            sentry_sdk.capture_exception(error=e)
            self._drop()
            return False

    def signum_canvas(self, material_code: Optional[str]) -> Tuple[int, int, int, int, int]:
        try:
            self._ensure_open()
        except Exception as e:
            sentry_sdk.capture_exception(error=e)
            self._drop()

        printable_width = self._printable_width_px or self._MediaWidthToTapeMargin.to_print_width(
            self._FALLBACK_TAPE_WIDTH_MM
        )
        length = self.signum_length_cd_pt if material_code == "3" else self.signum_length_pt
        return (
            length,
            printable_width,
            self.minimum_font_height_pt,
            self.signum_spacing_pt,
            self.font_stroke_width_pt,
        )


def _parse_bool(value: Any) -> bool:
    return str(value).lower() in ("true", "1", "yes", "on")


class Printer:
    """
    Orchestrator that selects a backend based on configuration and exposes a
    stable API to the application: `discover_printer()` and `print_signum()`.
    """

    def __init__(self, config_manager):
        self.state: PrinterState = PrinterState.NO_PRINTER_CONNECTED
        self.device: Optional[Dict[str, Any]] = None

        self.font_path: str = str(config_manager.get("printer", "font_path") or "assets/arialn.ttf")

        backend_name = str(config_manager.get("printer", "backend") or "ql").strip().lower()
        self.backend_name = backend_name

        if backend_name == "pt":
            serial_value = str(config_manager.get("printer", "serial") or "").strip()
            self.backend: PrinterBackend = BrotherPTBackend(
                serial=serial_value or None,
                margin_px=int(config_manager.get("printer", "margin_px", int) or 0),
                signum_length_pt=int(config_manager.get("printer", "signum_length_pt", int) or 200),
                signum_length_cd_pt=int(
                    config_manager.get("printer", "signum_length_cd_pt", int) or 120
                ),
                minimum_font_height_pt=int(
                    config_manager.get("printer", "minimum_font_height_pt", int) or 30
                ),
                signum_spacing_pt=int(config_manager.get("printer", "signum_spacing_pt", int) or 6),
                font_stroke_width_pt=int(
                    config_manager.get("printer", "font_stroke_width_pt", int) or 0
                ),
                cut_mode=str(config_manager.get("printer", "cut_mode") or "auto"),
            )
        else:
            self.backend = BrotherQLBackend(
                model=config_manager.get("printer", "model"),
                label=config_manager.get("printer", "label", str),
                red=bool(config_manager.get("printer", "red", _parse_bool) or False),
                dpi_600=bool(config_manager.get("printer", "dpi_600", _parse_bool) or False),
                hq=bool(config_manager.get("printer", "hq", _parse_bool) or False),
                dither=bool(config_manager.get("printer", "dither", _parse_bool) or False),
                compress=bool(config_manager.get("printer", "compress", _parse_bool) or False),
                signum_height=int(config_manager.get("printer", "signum_height", int) or 42),
                signum_height_cd=int(config_manager.get("printer", "signum_height_cd", int) or 40),
                minimum_font_height=int(
                    config_manager.get("printer", "minimum_font_height", int) or 32
                ),
                signum_spacing=int(config_manager.get("printer", "signum_spacing", int) or 10),
                font_stroke_width=int(config_manager.get("printer", "font_stroke_width", int) or 0),
            )

    def discover_printer(self) -> PrintResult:
        """
        Discovers the configured printer.

        :return: PrintResult with current state and device info.
        """
        result = self.backend.discover()
        self.state = result.state
        self.device = result.device
        return result

    def print_signum(
        self, classification: str, shelfmark: str, material_code: Optional[str] = None
    ) -> bool:
        """
        Creates and prints a signum label using the active backend.
        """
        if self.state != PrinterState.PRINTER_CONNECTED:
            return False

        try:
            width, height, min_font, spacing, stroke = self.backend.signum_canvas(material_code)
            image = create_signum(
                classification=classification,
                shelfmark=shelfmark,
                font_path=self.font_path,
                minimum_font_height=min_font,
                width=width,
                height=height,
                spacing=spacing,
                stroke_width=stroke,
                cd_wrap_expansion=self.backend.cd_wrap_expansion,
                auto_width=self.backend.auto_width,
            )
            # Uncomment to preview the rendered signum:
            # image.show()
            return self.backend.print_image(image)
        except Exception as e:
            print(e)
            sentry_sdk.capture_exception(error=e)
            return False
