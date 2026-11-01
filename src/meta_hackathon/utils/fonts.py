"""The font for Bangla text drawn on images, the same one the web UI uses."""

from pathlib import Path

from PIL import ImageFont

_ANEK_BANGLA = Path(__file__).parent.parent / "assets" / "fonts" / "AnekBangla-Variable.ttf"


def bangla_font(size: int) -> ImageFont.FreeTypeFont:
    """SemiBold: one file holds every weight, and labels on photos need the weight to stay legible."""
    font = ImageFont.truetype(str(_ANEK_BANGLA), size)
    font.set_variation_by_name("SemiBold")
    return font
