"""Generates a stylised PNG "card" for a player using Pillow only.

No official artwork is used anywhere: cards are pure vector-style
graphics (gradient background, a procedurally generated portrait emblem,
stat bars, text) so the bot can ship without any copyrighted image
assets. Uses Pillow's bundled default font, so no external .ttf
download is required.
"""
from __future__ import annotations

import io
from dataclasses import dataclass

from PIL import Image, ImageDraw, ImageFont

import config
from utils.portrait import ELEMENT_COLORS, paste_circular, render_portrait

CARD_W, CARD_H = 640, 920

STAT_LABELS = [
    ("kick", "TIR"),
    ("pass_", "PASSE"),
    ("defense", "DÉF"),
    ("speed", "VIT"),
    ("technique", "TECH"),
]


def _font(size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        # Older Pillow without the `size` kwarg on load_default().
        return ImageFont.load_default()


def _lerp(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))  # type: ignore[return-value]


def _vertical_gradient(draw: ImageDraw.ImageDraw, box, top_color, bottom_color):
    x0, y0, x1, y1 = box
    height = y1 - y0
    for i in range(height):
        t = i / max(height - 1, 1)
        draw.line([(x0, y0 + i), (x1, y0 + i)], fill=_lerp(top_color, bottom_color, t))


def _draw_stat_bar(draw, x, y, w, h, value, max_value, color, label, font):
    draw.rounded_rectangle([x, y, x + w, y + h], radius=h // 2, fill=(255, 255, 255, 40))
    fill_w = int(w * min(value / max_value, 1.0))
    if fill_w > 0:
        draw.rounded_rectangle([x, y, x + max(fill_w, h), y + h], radius=h // 2, fill=color)
    draw.text((x, y - 22), f"{label}", font=font, fill=(255, 255, 255))
    draw.text((x + w - 34, y - 22), str(value), font=font, fill=(255, 255, 255))


@dataclass
class CardData:
    name: str
    name_en: str
    position: str
    team_origin: str
    series: str
    element: str
    rarity: int
    kick: int
    pass_: int
    defense: int
    speed: int
    technique: int
    overall: int
    base_price: int = 0
    player_id: str = ""
    technique_name: str | None = None


def render_player_card(data: CardData) -> io.BytesIO:
    top_color = config.RARITY_COLORS.get(data.rarity, config.RARITY_COLORS[1])
    bottom_color = _lerp(top_color, (10, 10, 15), 0.75)

    img = Image.new("RGB", (CARD_W, CARD_H), bottom_color)
    draw = ImageDraw.Draw(img, "RGBA")
    _vertical_gradient(draw, (0, 0, CARD_W, CARD_H), top_color, bottom_color)

    # Border
    draw.rounded_rectangle([6, 6, CARD_W - 6, CARD_H - 6], radius=28, outline=(255, 255, 255), width=6)

    font_xl = _font(42)
    font_lg = _font(30)
    font_md = _font(23)
    font_sm = _font(19)

    # Rarity stars
    stars = config.RARITY_STARS.get(data.rarity, "⭐")
    draw.text((36, 28), stars, font=font_lg, fill=(255, 255, 255))

    # Overall rating badge (top right)
    badge_r = 50
    bx, by = CARD_W - 36 - badge_r * 2, 24
    draw.ellipse([bx, by, bx + badge_r * 2, by + badge_r * 2], fill=(0, 0, 0, 160), outline=(255, 255, 255), width=3)
    draw.text((bx + badge_r, by + badge_r - 18), str(data.overall), font=font_xl, fill=(255, 255, 255), anchor="mm")
    draw.text((bx + badge_r, by + badge_r + 20), data.position, font=font_sm, fill=(255, 255, 255), anchor="mm")

    # Procedurally generated portrait, top-left.
    portrait_size = 176
    portrait_pos = (36, 82)
    portrait = render_portrait(data.player_id or data.name, data.position, data.element, data.rarity, size=portrait_size)
    paste_circular(img, portrait, portrait_pos)

    # Name block, to the right of the portrait.
    name_x = portrait_pos[0] + portrait_size + 22
    name_w = CARD_W - 36 - name_x
    draw.text((name_x, 92), data.name, font=font_xl, fill=(255, 255, 255))
    draw.text((name_x, 140), data.name_en, font=font_md, fill=(230, 230, 230))
    draw.text((name_x, 180), f"{data.team_origin}", font=font_sm, fill=(255, 255, 255))
    draw.text((name_x, 206), data.series, font=font_sm, fill=(220, 220, 220))

    elem_color = ELEMENT_COLORS.get(data.element, (200, 200, 200))
    draw.ellipse([name_x, 236, name_x + 22, 258], fill=elem_color, outline=(255, 255, 255), width=2)
    draw.text((name_x + 30, 236), data.element, font=font_sm, fill=(255, 255, 255))

    # Divider
    draw.line([(36, 282), (CARD_W - 36, 282)], fill=(255, 255, 255, 120), width=2)

    # Stat bars
    bar_x = 36
    bar_w = CARD_W - 72
    bar_h = 22
    start_y = 330
    gap = 60
    accent = (255, 255, 255)
    for i, (attr, label) in enumerate(STAT_LABELS):
        value = getattr(data, attr)
        _draw_stat_bar(draw, bar_x, start_y + i * gap, bar_w, bar_h, value, 99, accent, label, font_sm)

    # Market value row
    value_y = start_y + len(STAT_LABELS) * gap + 20
    draw.line([(36, value_y - 14), (CARD_W - 36, value_y - 14)], fill=(255, 255, 255, 120), width=2)
    resale = round(data.base_price * config.PLAYER_SELL_RATE)
    half_w = (CARD_W - 72) / 2
    draw.text((36, value_y), "VALEUR", font=font_sm, fill=(220, 220, 220))
    draw.text((36, value_y + 24), f"{data.base_price:,} {config.CURRENCY_SYMBOL}".replace(",", " "), font=font_md, fill=(255, 255, 255))
    draw.text((36 + half_w, value_y), "REVENTE (40%)", font=font_sm, fill=(220, 220, 220))
    draw.text((36 + half_w, value_y + 24), f"{resale:,} {config.CURRENCY_SYMBOL}".replace(",", " "), font=font_md, fill=(255, 255, 255))

    # Signature technique footer
    footer_y = value_y + 74
    draw.line([(36, footer_y - 14), (CARD_W - 36, footer_y - 14)], fill=(255, 255, 255, 120), width=2)
    draw.text((36, footer_y), "TECHNIQUE SIGNATURE", font=font_sm, fill=(220, 220, 220))
    draw.text((36, footer_y + 26), data.technique_name or "—", font=font_md, fill=(255, 255, 255))

    # INAZUMA BOT watermark
    draw.text((CARD_W - 36, CARD_H - 30), "INAZUMA BOT", font=font_sm, fill=(255, 255, 255, 180), anchor="rs")

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf
