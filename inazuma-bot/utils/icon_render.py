"""Procedurally generated "cards" for techniques and coaches (Pillow only,
no external assets) — same spirit as utils/card_render.py and
utils/portrait.py: every technique/coach gets a unique, deterministic
picture without using any official artwork.
"""
from __future__ import annotations

import hashlib
import io
import random
from dataclasses import dataclass

from PIL import Image, ImageDraw, ImageFont

import config
from utils.portrait import ELEMENT_COLORS, JERSEY_PALETTE, _seeded_rng

CARD_W, CARD_H = 560, 640

TYPE_LABELS = {"shoot": "TIR", "dribble": "DRIBBLE", "block": "BLOCAGE", "catch": "PARADE"}

_LIGHTNING = [(0.60, 0.0), (0.25, 0.55), (0.50, 0.55), (0.20, 1.0), (0.85, 0.40), (0.55, 0.40)]
_SHIELD = [(0.5, 0.0), (1.0, 0.16), (1.0, 0.58), (0.5, 1.0), (0.0, 0.58), (0.0, 0.16)]


def _font(size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _lerp(a, b, t: float):
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _vertical_gradient(draw, box, top_color, bottom_color):
    x0, y0, x1, y1 = box
    height = y1 - y0
    for i in range(height):
        t = i / max(height - 1, 1)
        draw.line([(x0, y0 + i), (x1, y0 + i)], fill=_lerp(top_color, bottom_color, t))


def _map_pts(fracs, box):
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    return [(x0 + fx * w, y0 + fy * h) for fx, fy in fracs]


def _draw_type_glyph(draw: ImageDraw.ImageDraw, type_: str, box, color) -> None:
    x0, y0, x1, y1 = box
    if type_ == "shoot":
        draw.polygon(_map_pts(_LIGHTNING, box), fill=color)
    elif type_ == "block":
        draw.polygon(_map_pts(_SHIELD, box), fill=color)
    elif type_ == "catch":
        w, h = x1 - x0, y1 - y0
        draw.rounded_rectangle([x0 + w * 0.18, y0 + h * 0.30, x1 - w * 0.05, y1], radius=int(w * 0.18), fill=color)
        draw.ellipse([x0, y0 + h * 0.12, x0 + w * 0.38, y0 + h * 0.55], fill=color)
    else:  # dribble
        w, h = x1 - x0, y1 - y0
        lw = max(6, int(w * 0.10))
        draw.arc([x0, y0 + h * 0.10, x1 - w * 0.25, y1 - h * 0.15], start=200, end=340, fill=color, width=lw)
        draw.arc([x0 + w * 0.25, y0 + h * 0.35, x1, y1 + h * 0.10], start=20, end=160, fill=color, width=lw)
        r = w * 0.09
        draw.ellipse([x1 - r * 2.2, y1 - h * 0.25 - r, x1 - r * 0.2, y1 - h * 0.25 + r], fill=color)


@dataclass
class TechniqueData:
    id: str
    name: str
    type: str
    element: str
    power: int
    rarity: int
    description: str


def render_technique_card(data: TechniqueData) -> io.BytesIO:
    top_color = config.RARITY_COLORS.get(data.rarity, config.RARITY_COLORS[1])
    bottom_color = _lerp(top_color, (10, 10, 15), 0.75)

    img = Image.new("RGB", (CARD_W, CARD_H), bottom_color)
    draw = ImageDraw.Draw(img, "RGBA")
    _vertical_gradient(draw, (0, 0, CARD_W, CARD_H), top_color, bottom_color)
    draw.rounded_rectangle([6, 6, CARD_W - 6, CARD_H - 6], radius=26, outline=(255, 255, 255), width=5)

    font_xl, font_lg, font_md, font_sm = _font(34), _font(26), _font(21), _font(18)

    draw.text((30, 24), config.RARITY_STARS.get(data.rarity, "⭐") + f" ({data.rarity}/5)", font=font_lg, fill=(255, 255, 255))
    draw.text((CARD_W - 30, 24), TYPE_LABELS.get(data.type, data.type.upper()), font=font_lg, fill=(255, 255, 255), anchor="ra")

    # Icon medallion, centered.
    med_size = 220
    med_box = (CARD_W // 2 - med_size // 2, 80, CARD_W // 2 + med_size // 2, 80 + med_size)
    elem_color = ELEMENT_COLORS.get(data.element, (150, 150, 150))
    draw.ellipse(med_box, fill=elem_color)
    inner = (med_box[0] + 10, med_box[1] + 10, med_box[2] - 10, med_box[3] - 10)
    draw.ellipse(inner, fill=_lerp(elem_color, (10, 10, 14), 0.55))
    if data.rarity == 5:
        draw.ellipse(med_box, outline=(255, 215, 0), width=5)

    glyph_pad = med_size * 0.27
    glyph_box = (med_box[0] + glyph_pad, med_box[1] + glyph_pad, med_box[2] - glyph_pad, med_box[3] - glyph_pad)
    silhouette = _lerp(elem_color, (255, 255, 255), 0.55)
    _draw_type_glyph(draw, data.type, glyph_box, silhouette)

    name_y = med_box[3] + 26
    draw.text((CARD_W / 2, name_y), data.name, font=font_xl, fill=(255, 255, 255), anchor="ma")
    draw.text((CARD_W / 2, name_y + 44), data.element, font=font_sm, fill=(220, 220, 220), anchor="ma")

    # Power gauge
    gauge_y = name_y + 84
    gauge_x, gauge_w, gauge_h = 40, CARD_W - 80, 24
    draw.text((gauge_x, gauge_y - 24), "PUISSANCE", font=font_sm, fill=(220, 220, 220))
    draw.text((gauge_x + gauge_w - 34, gauge_y - 24), str(data.power), font=font_sm, fill=(255, 255, 255))
    draw.rounded_rectangle([gauge_x, gauge_y, gauge_x + gauge_w, gauge_y + gauge_h], radius=gauge_h // 2, fill=(255, 255, 255, 40))
    fill_w = int(gauge_w * min(data.power / 99, 1.0))
    if fill_w > 0:
        draw.rounded_rectangle([gauge_x, gauge_y, gauge_x + max(fill_w, gauge_h), gauge_y + gauge_h], radius=gauge_h // 2, fill=(255, 255, 255))

    # Description
    desc_y = gauge_y + 60
    draw.line([(40, desc_y - 14), (CARD_W - 40, desc_y - 14)], fill=(255, 255, 255, 120), width=2)
    wrapped = _wrap_text(data.description, font_sm, CARD_W - 80)
    for i, line in enumerate(wrapped[:4]):
        draw.text((40, desc_y + i * 24), line, font=font_sm, fill=(230, 230, 230))

    draw.text((CARD_W - 30, CARD_H - 26), "INAZUMA BOT", font=font_sm, fill=(255, 255, 255, 180), anchor="rs")

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


@dataclass
class CoachData:
    id: str
    name: str
    team_origin: str
    bonus: dict
    rarity: int
    description: str


def render_coach_card(data: CoachData) -> io.BytesIO:
    top_color = config.RARITY_COLORS.get(data.rarity, config.RARITY_COLORS[1])
    bottom_color = _lerp(top_color, (10, 10, 15), 0.75)

    img = Image.new("RGB", (CARD_W, CARD_H), bottom_color)
    draw = ImageDraw.Draw(img, "RGBA")
    _vertical_gradient(draw, (0, 0, CARD_W, CARD_H), top_color, bottom_color)
    draw.rounded_rectangle([6, 6, CARD_W - 6, CARD_H - 6], radius=26, outline=(255, 255, 255), width=5)

    font_xl, font_lg, font_md, font_sm = _font(34), _font(26), _font(21), _font(18)

    draw.text((30, 24), config.RARITY_STARS.get(data.rarity, "⭐") + f" ({data.rarity}/5)", font=font_lg, fill=(255, 255, 255))
    draw.text((CARD_W - 30, 24), "COACH", font=font_lg, fill=(255, 255, 255), anchor="ra")

    # Portrait: a "suit" silhouette instead of a jersey.
    rng = _seeded_rng(data.id)
    med_size = 220
    cx = CARD_W // 2
    med_box = (cx - med_size // 2, 80, cx + med_size // 2, 80 + med_size)
    team_color = rng.choice(JERSEY_PALETTE)
    draw.ellipse(med_box, fill=team_color)
    inner = (med_box[0] + 10, med_box[1] + 10, med_box[2] - 10, med_box[3] - 10)
    bg = _lerp(team_color, (10, 10, 14), 0.6)
    draw.ellipse(inner, fill=bg)
    if data.rarity == 5:
        draw.ellipse(med_box, outline=(255, 215, 0), width=5)

    silhouette = _lerp(team_color, (0, 0, 0), 0.7)
    head_r = med_size * 0.14
    head_cy = med_box[1] + med_size * 0.35
    draw.ellipse([cx - head_r, head_cy - head_r, cx + head_r, head_cy + head_r], fill=silhouette)
    shoulder_w = med_size * 0.42
    suit_top = med_box[1] + med_size * 0.5
    suit_bottom = med_box[3] - med_size * 0.05
    draw.polygon(
        [
            (cx - shoulder_w / 2, suit_top + med_size * 0.05),
            (cx, suit_top),
            (cx + shoulder_w / 2, suit_top + med_size * 0.05),
            (cx + shoulder_w * 0.35, suit_bottom),
            (cx - shoulder_w * 0.35, suit_bottom),
        ],
        fill=silhouette,
    )
    draw.polygon([(cx - 10, suit_top + 4), (cx + 10, suit_top + 4), (cx, suit_top + 34)], fill=team_color)

    name_y = med_box[3] + 26
    draw.text((cx, name_y), data.name, font=font_xl, fill=(255, 255, 255), anchor="ma")
    draw.text((cx, name_y + 44), data.team_origin, font=font_sm, fill=(220, 220, 220), anchor="ma")

    bonus_y = name_y + 90
    draw.line([(40, bonus_y - 16), (CARD_W - 40, bonus_y - 16)], fill=(255, 255, 255, 120), width=2)
    bonus_text = "  ".join(f"{k.upper()} {'+' if v >= 0 else ''}{v}" for k, v in data.bonus.items())
    draw.text((CARD_W / 2, bonus_y), bonus_text or "—", font=font_md, fill=(255, 255, 255), anchor="ma")

    desc_y = bonus_y + 46
    wrapped = _wrap_text(data.description, font_sm, CARD_W - 80)
    for i, line in enumerate(wrapped[:4]):
        draw.text((40, desc_y + i * 24), line, font=font_sm, fill=(230, 230, 230))

    draw.text((CARD_W - 30, CARD_H - 26), "INAZUMA BOT", font=font_sm, fill=(255, 255, 255, 180), anchor="rs")

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


def _wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        trial = f"{current} {word}".strip()
        if font.getlength(trial) <= max_width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines
