"""Procedurally generated player "portraits" — a deterministic abstract emblem
(colored ring, silhouette wearing a numbered jersey, position badge) derived
from the player's id. No official artwork, no photo/likeness of any kind —
every player still gets a unique, consistent picture on their card.
"""
from __future__ import annotations

import hashlib
import math
import random

from PIL import Image, ImageDraw, ImageFont

ELEMENT_COLORS = {
    "Fire": (244, 67, 54),
    "Wind": (76, 175, 80),
    "Wood": (121, 85, 72),
    "Earth": (255, 152, 0),
}

JERSEY_PALETTE = [
    (255, 235, 59),
    (33, 150, 243),
    (233, 30, 99),
    (0, 188, 212),
    (255, 87, 34),
    (139, 195, 74),
    (156, 39, 176),
    (255, 255, 255),
    (255, 193, 7),
    (0, 150, 136),
]

POSITION_LABEL = {"GK": "GK", "DF": "DF", "MF": "MF", "FW": "FW"}


def _seeded_rng(seed_str: str) -> random.Random:
    digest = hashlib.sha256(seed_str.encode("utf-8")).hexdigest()
    return random.Random(int(digest, 16))


def _lerp(a, b, t: float):
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _font(size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _brightness(color) -> float:
    r, g, b = color[:3]
    return (0.299 * r + 0.587 * g + 0.114 * b) / 255


def render_portrait(player_id: str, position: str, element: str, rarity: int, size: int = 220) -> Image.Image:
    rng = _seeded_rng(player_id)
    elem_color = ELEMENT_COLORS.get(element, (150, 150, 150))

    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img, "RGBA")

    # Outer element-colored ring, inner dark disk to host the silhouette.
    draw.ellipse([0, 0, size, size], fill=elem_color)
    ring_w = max(6, size // 22)
    inner_bg = _lerp(elem_color, (10, 10, 14), 0.55)
    draw.ellipse([ring_w, ring_w, size - ring_w, size - ring_w], fill=inner_bg)

    # Rarity accent ring for 4-5 star cards.
    if rarity >= 4:
        accent = (255, 215, 0) if rarity == 5 else (210, 210, 220)
        draw.ellipse([2, 2, size - 2, size - 2], outline=accent, width=4)

    silhouette = _lerp(elem_color, (0, 0, 0), 0.72)
    cx = size / 2

    # Head.
    head_r = size * 0.15
    head_cy = size * 0.34
    draw.ellipse([cx - head_r, head_cy - head_r, cx + head_r, head_cy + head_r], fill=silhouette)

    # Shoulders + torso silhouette (rounded trapezoid via polygon).
    torso_top = size * 0.46
    torso_bottom = size * 0.88
    shoulder_w = size * 0.40
    waist_w = size * 0.30
    draw.polygon(
        [
            (cx - shoulder_w / 2, torso_top + size * 0.06),
            (cx - shoulder_w * 0.28, torso_top),
            (cx + shoulder_w * 0.28, torso_top),
            (cx + shoulder_w / 2, torso_top + size * 0.06),
            (cx + waist_w / 2, torso_bottom),
            (cx - waist_w / 2, torso_bottom),
        ],
        fill=silhouette,
    )

    # Jersey overlay on the torso, with a V-neck cutout and a random number.
    jersey_color = rng.choice(JERSEY_PALETTE)
    jersey_top = torso_top + size * 0.10
    jersey_w = waist_w * 1.05
    draw.polygon(
        [
            (cx - jersey_w / 2, jersey_top + size * 0.05),
            (cx - jersey_w * 0.22, jersey_top),
            (cx, jersey_top + size * 0.05),
            (cx + jersey_w * 0.22, jersey_top),
            (cx + jersey_w / 2, jersey_top + size * 0.05),
            (cx + waist_w / 2 * 0.96, torso_bottom - 2),
            (cx - waist_w / 2 * 0.96, torso_bottom - 2),
        ],
        fill=jersey_color,
    )

    number = rng.randint(1, 99)
    number_color = (25, 25, 30) if _brightness(jersey_color) > 0.55 else (255, 255, 255)
    font = _font(int(size * 0.16))
    draw.text((cx, (jersey_top + torso_bottom) / 2 + size * 0.03), str(number), font=font, fill=number_color, anchor="mm")

    # Position badge, bottom-right.
    badge_r = size * 0.14
    bx, by = size - badge_r * 1.5, size - badge_r * 1.5
    draw.ellipse([bx - badge_r, by - badge_r, bx + badge_r, by + badge_r], fill=(15, 15, 20), outline=(255, 255, 255), width=2)
    draw.text((bx, by), POSITION_LABEL.get(position, "?"), font=_font(int(size * 0.10)), fill=(255, 255, 255), anchor="mm")

    return img


def paste_circular(base_img: Image.Image, portrait: Image.Image, top_left: tuple[int, int]) -> None:
    """Pastes a square portrait onto base_img, clipped to a circle."""
    size = portrait.size[0]
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, size, size], fill=255)
    base_img.paste(portrait, top_left, mask)
