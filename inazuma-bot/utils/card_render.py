"""Generates a stylised PNG "card" for a player using Pillow only.

No official artwork is used anywhere: cards are pure vector-style
graphics (gradient background, a procedurally generated portrait emblem,
stat bars, text) so the bot can ship without any copyrighted image
assets. Uses Pillow's bundled default font, so no external .ttf
download is required.

The western/French dub name (`name_en`) is shown as the primary,
large title, with the Japanese name underneath as a secondary line —
matching how players actually know these characters.
"""
from __future__ import annotations

import io
from dataclasses import dataclass

from PIL import Image, ImageDraw, ImageFont

import config
from utils.portrait import ELEMENT_COLORS, paste_circular, render_portrait

CARD_W, CARD_H = 680, 1180

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
    draw.text((x, y - 24), f"{label}", font=font, fill=(255, 255, 255))
    draw.text((x + w - 34, y - 24), str(value), font=font, fill=(255, 255, 255))


def _draw_centered_pill(draw, cx, y, text, color, font):
    dot_r = 12
    text_w = font.getlength(text)
    total_w = dot_r * 2 + 10 + text_w
    x0 = cx - total_w / 2
    draw.ellipse([x0, y, x0 + dot_r * 2, y + dot_r * 2], fill=color, outline=(255, 255, 255), width=2)
    draw.text((x0 + dot_r * 2 + 10, y - 4), text, font=font, fill=(255, 255, 255))


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
    draw.rounded_rectangle([6, 6, CARD_W - 6, CARD_H - 6], radius=30, outline=(255, 255, 255), width=6)

    font_xxl = _font(52)
    font_xl = _font(38)
    font_lg = _font(30)
    font_md = _font(23)
    font_sm = _font(19)

    cx = CARD_W / 2

    # Rarity stars (top-left) and overall badge (top-right).
    stars = config.RARITY_STARS.get(data.rarity, "⭐")
    draw.text((36, 28), stars, font=font_lg, fill=(255, 255, 255))

    badge_r = 52
    bx, by = CARD_W - 36 - badge_r * 2, 24
    draw.ellipse([bx, by, bx + badge_r * 2, by + badge_r * 2], fill=(0, 0, 0, 160), outline=(255, 255, 255), width=3)
    draw.text((bx + badge_r, by + badge_r - 19), str(data.overall), font=font_xl, fill=(255, 255, 255), anchor="mm")
    draw.text((bx + badge_r, by + badge_r + 21), data.position, font=font_sm, fill=(255, 255, 255), anchor="mm")

    # Big, centered, procedurally generated portrait.
    portrait_size = 300
    portrait_top = 90
    portrait_pos = (int(cx - portrait_size / 2), portrait_top)
    portrait = render_portrait(data.player_id or data.name, data.position, data.element, data.rarity, size=portrait_size)
    paste_circular(img, portrait, portrait_pos)

    # Name block, centered below the portrait — western/French name first (large),
    # Japanese name underneath as a secondary line.
    name_y = portrait_top + portrait_size + 26
    draw.text((cx, name_y), data.name_en, font=font_xxl, fill=(255, 255, 255), anchor="ma")
    draw.text((cx, name_y + 60), data.name, font=font_md, fill=(210, 210, 210), anchor="ma")
    draw.text((cx, name_y + 92), f"{data.team_origin} — {data.series}", font=font_sm, fill=(225, 225, 225), anchor="ma")

    elem_color = ELEMENT_COLORS.get(data.element, (200, 200, 200))
    _draw_centered_pill(draw, cx, name_y + 122, data.element, elem_color, font_sm)

    # Divider
    divider_y = name_y + 168
    draw.line([(36, divider_y), (CARD_W - 36, divider_y)], fill=(255, 255, 255, 120), width=2)

    # Stat bars
    bar_x = 46
    bar_w = CARD_W - 92
    bar_h = 24
    start_y = divider_y + 46
    gap = 64
    accent = (255, 255, 255)
    for i, (attr, label) in enumerate(STAT_LABELS):
        value = getattr(data, attr)
        _draw_stat_bar(draw, bar_x, start_y + i * gap, bar_w, bar_h, value, 99, accent, label, font_sm)

    # Market value row
    value_y = start_y + len(STAT_LABELS) * gap + 22
    draw.line([(36, value_y - 14), (CARD_W - 36, value_y - 14)], fill=(255, 255, 255, 120), width=2)
    resale = round(data.base_price * config.PLAYER_SELL_RATE)
    half_w = (CARD_W - 92) / 2
    draw.text((bar_x, value_y), "VALEUR", font=font_sm, fill=(220, 220, 220))
    draw.text((bar_x, value_y + 26), f"{data.base_price:,} {config.CURRENCY_SYMBOL}".replace(",", " "), font=font_md, fill=(255, 255, 255))
    draw.text((bar_x + half_w, value_y), "REVENTE (40%)", font=font_sm, fill=(220, 220, 220))
    draw.text((bar_x + half_w, value_y + 26), f"{resale:,} {config.CURRENCY_SYMBOL}".replace(",", " "), font=font_md, fill=(255, 255, 255))

    # Signature technique footer
    footer_y = value_y + 78
    draw.line([(36, footer_y - 14), (CARD_W - 36, footer_y - 14)], fill=(255, 255, 255, 120), width=2)
    draw.text((bar_x, footer_y), "TECHNIQUE SIGNATURE", font=font_sm, fill=(220, 220, 220))
    draw.text((bar_x, footer_y + 28), data.technique_name or "—", font=font_md, fill=(255, 255, 255))

    # INAZUMA BOT watermark
    draw.text((CARD_W - 36, CARD_H - 30), "INAZUMA BOT", font=font_sm, fill=(255, 255, 255, 180), anchor="rs")

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf
