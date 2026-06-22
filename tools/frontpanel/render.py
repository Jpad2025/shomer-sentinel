"""Genera logo-portrait.png (170×280) para pantalla frontal AceMagic S1."""
from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

BG = (13, 26, 42, 255)
TEAL = (13, 110, 110, 255)
GREEN = (71, 179, 32, 255)
AMBER = (217, 119, 6, 255)
RED = (220, 38, 38, 255)
MUTED = (120, 140, 160, 255)

W, H = 170, 280


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ):
        if Path(path).is_file():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _wan_color(status: str) -> Tuple[int, int, int, int]:
    s = (status or "unknown").lower()
    if s in ("online", "ok"):
        return GREEN
    if s in ("degraded", "unknown"):
        return AMBER
    return RED


def _wan_label(status: str) -> str:
    s = (status or "unknown").lower()
    labels = {
        "online": "WAN OK",
        "ok": "WAN OK",
        "offline": "WAN CAIDA",
        "no-internet": "SIN INTERNET",
        "degraded": "WAN DEGRADADA",
        "unknown": "WAN ?",
    }
    return labels.get(s, f"WAN {s.upper()[:12]}")


def render_logo_portrait(
    usb_src: Path,
    shomer_src: Path,
    out_path: Path,
    *,
    status_wan: Optional[str] = None,
    status_aps: Optional[str] = None,
    site_name: Optional[str] = None,
    show_status: bool = True,
) -> None:
    """Compone USB + Shomer (+ líneas de estado opcionales) en PNG portrait."""
    bg = Image.new("RGBA", (W, H), BG)
    draw = ImageDraw.Draw(bg)

    usb = Image.open(usb_src).convert("RGBA")
    shomer = Image.open(shomer_src).convert("RGBA")

    usb_max_w, usb_zone_h = W - 16, 56
    uw, uh = usb.size
    usb_scale = min(usb_max_w / uw, (usb_zone_h - 4) / uh)
    unw, unh = int(uw * usb_scale), int(uh * usb_scale)
    usb = usb.resize((unw, unh), Image.LANCZOS)
    bg.paste(usb, ((W - unw) // 2, 8), usb)

    y = 8 + unh + 4
    if show_status and (status_wan or status_aps or site_name):
        f_sm = _font(10)
        f_md = _font(11)
        if site_name:
            draw.text((W // 2, y), site_name[:22], fill=TEAL, font=f_sm, anchor="mt")
            y += 13
        if status_wan:
            draw.text(
                (W // 2, y),
                _wan_label(status_wan),
                fill=_wan_color(status_wan),
                font=f_md,
                anchor="mt",
            )
            y += 14
        if status_aps:
            draw.text((W // 2, y), status_aps, fill=GREEN, font=f_sm, anchor="mt")
            y += 12
        y += 4

    shomer_zone_h = H - y - 6
    sw, sh = shomer.size
    shomer_scale = min((W - 12) / sw, shomer_zone_h / sh)
    snw, snh = int(sw * shomer_scale), int(sh * shomer_scale)
    shomer = shomer.resize((snw, snh), Image.LANCZOS)
    bg.paste(shomer, ((W - snw) // 2, y + (shomer_zone_h - snh) // 2), shomer)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    bg.convert("RGB").save(out_path)
