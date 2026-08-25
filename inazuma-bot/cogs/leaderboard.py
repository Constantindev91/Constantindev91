from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import select

import config
from db.database import SessionLocal
from db.models import User
from utils.pagination import Paginator, chunk


class LeaderboardCog(commands.Cog):
    """Classements du serveur : rang, richesse, victoires."""

    leaderboard_group = app_commands.Group(name="leaderboard", description="Classements du serveur")

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _render(self, interaction: discord.Interaction, title: str, users: list[User], value_fn, unit: str):
        pages = []
        for group in chunk(users, 10):
            lines = []
            start = users.index(group[0]) + 1
            for i, u in enumerate(group, start=start):
                member = interaction.guild.get_member(u.discord_id) if interaction.guild else None
                name = member.display_name if member else f"<@{u.discord_id}>"
                medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(i, f"`#{i}`")
                lines.append(f"{medal} {name} — **{f'{value_fn(u)} {unit}'.strip()}**")
            embed = discord.Embed(title=title, description="\n".join(lines), color=config.rarity_embed_color(5))
            pages.append(embed)
        await interaction.response.send_message(embed=pages[0], view=Paginator(interaction.user.id, pages))

    @leaderboard_group.command(name="rank", description="Classement par points de rang (ranked).")
    async def rank(self, interaction: discord.Interaction):
        async with SessionLocal() as session:
            users = list((await session.execute(select(User).order_by(User.rank_points.desc()).limit(100))).scalars().all())
        await self._render(interaction, "🏆 Classement Ranked", users, lambda u: f"{u.rank_points} pts ({config.rank_tier_for_points(u.rank_points)})", "")

    @leaderboard_group.command(name="rich", description=f"Classement par {config.CURRENCY_NAME}.")
    async def rich(self, interaction: discord.Interaction):
        async with SessionLocal() as session:
            users = list((await session.execute(select(User).order_by(User.currency.desc()).limit(100))).scalars().all())
        await self._render(interaction, "💰 Classement Fortune", users, lambda u: u.currency, config.CURRENCY_SYMBOL)

    @leaderboard_group.command(name="wins", description="Classement par nombre de victoires en combat.")
    async def wins(self, interaction: discord.Interaction):
        async with SessionLocal() as session:
            users = list((await session.execute(select(User).order_by(User.wins.desc()).limit(100))).scalars().all())
        await self._render(interaction, "⚔️ Classement Victoires", users, lambda u: u.wins, "victoires")


async def setup(bot: commands.Bot):
    await bot.add_cog(LeaderboardCog(bot))
