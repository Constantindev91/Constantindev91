"""Configuration and game-balance constants for INAZUMA BOT."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT_DIR = Path(__file__).resolve().parent
DATA_DIR = ROOT_DIR / "data"
ASSETS_DIR = ROOT_DIR / "assets"

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "")
DEV_GUILD_ID = os.getenv("DEV_GUILD_ID") or None
DATABASE_PATH = os.getenv("DATABASE_PATH", "inazuma.db")
DATABASE_URL = f"sqlite+aiosqlite:///{DATABASE_PATH}"

CURRENCY_NAME = "Kizuna Points"
CURRENCY_SYMBOL = "KP"

# ---------------------------------------------------------------------------
# Claim system
# ---------------------------------------------------------------------------
CLAIM_COOLDOWN_SECONDS = 30 * 60  # 30 minutes
CLAIM_VIEW_TIMEOUT = 90  # seconds to decide keep/sell before auto-keep

# Weighted odds for claim pulls, keyed by rarity (must sum to 100)
RARITY_WEIGHTS = {
    1: 42,
    2: 30,
    3: 17,
    4: 8,
    5: 3,
}

RARITY_STARS = {
    1: "⭐",
    2: "⭐⭐",
    3: "⭐⭐⭐",
    4: "⭐⭐⭐⭐",
    5: "⭐⭐⭐⭐⭐",
}

# Hex colors per rarity, used for card borders / embed colors
RARITY_COLORS = {
    1: (158, 158, 158),   # gray
    2: (76, 175, 80),     # green
    3: (33, 150, 243),    # blue
    4: (156, 39, 176),    # purple
    5: (255, 193, 7),     # gold
}

def rarity_embed_color(rarity: int) -> int:
    r, g, b = RARITY_COLORS.get(rarity, RARITY_COLORS[1])
    return (r << 16) + (g << 8) + b

# ---------------------------------------------------------------------------
# Economy
# ---------------------------------------------------------------------------
STARTING_CURRENCY = 1000
DAILY_REWARD = 300
DAILY_COOLDOWN_SECONDS = 24 * 60 * 60

def sell_value(rarity: int) -> int:
    """Base KP earned from selling a card of a given rarity (+/- variance applied by caller)."""
    return {1: 80, 2: 200, 3: 450, 4: 900, 5: 2000}.get(rarity, 80)

def shop_price(rarity: int) -> int:
    """Base KP price to buy a technique/tactic/coach of a given rarity in the shop."""
    return {1: 150, 2: 350, 3: 700, 4: 1400, 5: 3000}.get(rarity, 150)

# Transfer market listing fee (like a league transfer tax) taken from the seller's proceeds
MARKET_TAX_RATE = 0.05
MARKET_MIN_PRICE = 20
MARKET_MAX_PRICE = 100_000

# ---------------------------------------------------------------------------
# Formations: slot_key -> (position_required, display label, (x, y) grid coords for rendering)
# Grid is 0..4 (x, left->right) by 0..4 (y, GK at y=4 to FW at y=0) just for layout purposes.
# ---------------------------------------------------------------------------
FORMATIONS: dict[str, list[tuple[str, str, str]]] = {
    "4-4-2": [
        ("GK", "GK", "Gardien"),
        ("DF", "DF1", "Défenseur G"),
        ("DF", "DF2", "Défenseur C1"),
        ("DF", "DF3", "Défenseur C2"),
        ("DF", "DF4", "Défenseur D"),
        ("MF", "MF1", "Milieu G"),
        ("MF", "MF2", "Milieu C1"),
        ("MF", "MF3", "Milieu C2"),
        ("MF", "MF4", "Milieu D"),
        ("FW", "FW1", "Attaquant G"),
        ("FW", "FW2", "Attaquant D"),
    ],
    "4-3-3": [
        ("GK", "GK", "Gardien"),
        ("DF", "DF1", "Défenseur G"),
        ("DF", "DF2", "Défenseur C1"),
        ("DF", "DF3", "Défenseur C2"),
        ("DF", "DF4", "Défenseur D"),
        ("MF", "MF1", "Milieu G"),
        ("MF", "MF2", "Milieu C"),
        ("MF", "MF3", "Milieu D"),
        ("FW", "FW1", "Ailier G"),
        ("FW", "FW2", "Buteur"),
        ("FW", "FW3", "Ailier D"),
    ],
    "3-5-2": [
        ("GK", "GK", "Gardien"),
        ("DF", "DF1", "Défenseur G"),
        ("DF", "DF2", "Défenseur C"),
        ("DF", "DF3", "Défenseur D"),
        ("MF", "MF1", "Milieu G"),
        ("MF", "MF2", "Milieu CG"),
        ("MF", "MF3", "Milieu C"),
        ("MF", "MF4", "Milieu CD"),
        ("MF", "MF5", "Milieu D"),
        ("FW", "FW1", "Attaquant G"),
        ("FW", "FW2", "Attaquant D"),
    ],
    "5-3-2": [
        ("GK", "GK", "Gardien"),
        ("DF", "DF1", "Défenseur G"),
        ("DF", "DF2", "Défenseur CG"),
        ("DF", "DF3", "Défenseur C"),
        ("DF", "DF4", "Défenseur CD"),
        ("DF", "DF5", "Défenseur D"),
        ("MF", "MF1", "Milieu G"),
        ("MF", "MF2", "Milieu C"),
        ("MF", "MF3", "Milieu D"),
        ("FW", "FW1", "Attaquant G"),
        ("FW", "FW2", "Attaquant D"),
    ],
    "4-5-1": [
        ("GK", "GK", "Gardien"),
        ("DF", "DF1", "Défenseur G"),
        ("DF", "DF2", "Défenseur C1"),
        ("DF", "DF3", "Défenseur C2"),
        ("DF", "DF4", "Défenseur D"),
        ("MF", "MF1", "Milieu G"),
        ("MF", "MF2", "Milieu CG"),
        ("MF", "MF3", "Milieu C"),
        ("MF", "MF4", "Milieu CD"),
        ("MF", "MF5", "Milieu D"),
        ("FW", "FW1", "Buteur"),
    ],
    "4-2-3-1": [
        ("GK", "GK", "Gardien"),
        ("DF", "DF1", "Défenseur G"),
        ("DF", "DF2", "Défenseur C1"),
        ("DF", "DF3", "Défenseur C2"),
        ("DF", "DF4", "Défenseur D"),
        ("MF", "MF1", "Sentinelle G"),
        ("MF", "MF2", "Sentinelle D"),
        ("MF", "MF3", "MOC G"),
        ("MF", "MF4", "MOC C"),
        ("MF", "MF5", "MOC D"),
        ("FW", "FW1", "Buteur"),
    ],
    "3-4-3": [
        ("GK", "GK", "Gardien"),
        ("DF", "DF1", "Défenseur G"),
        ("DF", "DF2", "Défenseur C"),
        ("DF", "DF3", "Défenseur D"),
        ("MF", "MF1", "Milieu G"),
        ("MF", "MF2", "Milieu CG"),
        ("MF", "MF3", "Milieu CD"),
        ("MF", "MF4", "Milieu D"),
        ("FW", "FW1", "Ailier G"),
        ("FW", "FW2", "Buteur"),
        ("FW", "FW3", "Ailier D"),
    ],
}

BENCH_SIZE = 7

# ---------------------------------------------------------------------------
# Ranked ladder
# ---------------------------------------------------------------------------
RANK_TIERS = [
    ("Bronze", 0),
    ("Argent", 200),
    ("Or", 500),
    ("Platine", 900),
    ("Diamant", 1400),
    ("Légende", 2000),
]

RANK_POINTS_WIN = 25
RANK_POINTS_LOSS = -15
RANK_POINTS_DRAW = 5
BATTLE_REWARD_WIN = 250
BATTLE_REWARD_LOSS = 80
BATTLE_REWARD_DRAW = 150

def rank_tier_for_points(points: int) -> str:
    tier = RANK_TIERS[0][0]
    for name, threshold in RANK_TIERS:
        if points >= threshold:
            tier = name
    return tier
