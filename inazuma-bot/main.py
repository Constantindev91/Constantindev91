"""INAZUMA BOT — entrypoint.

A Discord gacha/team-management bot themed on the Inazuma Eleven franchise:
claim players every 30 minutes, build your squad (formation/starters/bench),
equip techniques/tactics/coaches, trade and buy/sell on the transfer market,
and battle other members 1v1 in a ranked ladder.
"""
from __future__ import annotations

import asyncio
import logging

import discord
from discord.ext import commands

import config
from db.database import init_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("inazuma-bot")

INTENTS = discord.Intents.default()
INTENTS.message_content = False  # the bot is 100% slash-command based

COGS = [
    "cogs.profile",
    "cogs.claim",
    "cogs.collection",
    "cogs.team",
    "cogs.shop",
    "cogs.market",
    "cogs.trade",
    "cogs.battle",
    "cogs.leaderboard",
    "cogs.help",
]


class InazumaBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix=commands.when_mentioned, intents=INTENTS)

    async def setup_hook(self) -> None:
        await init_db()
        log.info("Base de données initialisée et données Inazuma chargées.")

        for cog in COGS:
            await self.load_extension(cog)
            log.info("Cog chargé : %s", cog)

        if config.DEV_GUILD_ID:
            # Publish to the dev guild instantly, then wipe the global registry so the
            # same commands don't also show up a second time via the ~1h global sync
            # (classic discord.py duplicate-slash-command trap when mixing the two).
            guild = discord.Object(id=int(config.DEV_GUILD_ID))
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            log.info("Commandes synchronisées sur le serveur de dev (%s) : %d", config.DEV_GUILD_ID, len(synced))

            self.tree.clear_commands(guild=None)
            wiped = await self.tree.sync()
            log.info("Registre global vidé (%d commandes globales restantes) pour éviter les doublons.", len(wiped))
        else:
            synced = await self.tree.sync()
            log.info("Commandes synchronisées globalement : %d (peut prendre jusqu'à 1h à se propager)", len(synced))

    async def on_ready(self) -> None:
        log.info("Connecté en tant que %s (ID: %s)", self.user, self.user.id if self.user else "?")
        await self.change_presence(activity=discord.Game(name="/help — Inazuma Eleven"))


async def main() -> None:
    if not config.DISCORD_TOKEN:
        raise SystemExit(
            "❌ DISCORD_TOKEN manquant. Copie .env.example vers .env et renseigne le token de ton bot."
        )
    bot = InazumaBot()
    async with bot:
        await bot.start(config.DISCORD_TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
