from __future__ import annotations

import datetime as dt

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import func, select

import config
from db.database import SessionLocal
from db.models import Team, UserCard
from db.repository import daily_on_cooldown, format_timedelta, get_or_create_user


class ProfileCog(commands.Cog):
    """Profil, argent et récompense quotidienne."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="start", description="Crée ton profil INAZUMA BOT et reçois ton équipe de départ.")
    async def start(self, interaction: discord.Interaction):
        async with SessionLocal() as session:
            user = await get_or_create_user(session, interaction.user.id)
            already = user.created_at is not None and (
                dt.datetime.utcnow() - user.created_at
            ).total_seconds() > 2
            await session.commit()

        embed = discord.Embed(
            title="⚽ Bienvenue dans INAZUMA BOT !",
            description=(
                f"Ton profil est prêt avec **{config.STARTING_CURRENCY} {config.CURRENCY_SYMBOL}** "
                f"et une équipe vide en formation **4-4-2**.\n\n"
                f"Utilise `/claim` pour recruter ton premier joueur (toutes les 30 minutes), "
                f"puis `/team` pour composer ton onze de départ.\n"
                f"Tape `/help` pour voir toutes les commandes."
            ),
            color=config.rarity_embed_color(3),
        )
        if already:
            embed.set_footer(text="Tu avais déjà un profil — le voici à nouveau.")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="profile", description="Affiche ton profil (ou celui d'un autre joueur).")
    @app_commands.describe(member="Le membre à consulter (optionnel)")
    async def profile(self, interaction: discord.Interaction, member: discord.Member | None = None):
        target = member or interaction.user
        async with SessionLocal() as session:
            user = await get_or_create_user(session, target.id)
            card_count = await session.scalar(
                select(func.count()).select_from(UserCard).where(UserCard.owner_id == target.id)
            )
            team = await session.get(Team, user.active_team_id) if user.active_team_id else None
            await session.commit()

        tier = config.rank_tier_for_points(user.rank_points)
        embed = discord.Embed(title=f"📋 Profil de {target.display_name}", color=config.rarity_embed_color(4))
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="💰 Portefeuille", value=f"{user.currency} {config.CURRENCY_SYMBOL}", inline=True)
        embed.add_field(name="🏆 Rang", value=f"{tier} ({user.rank_points} pts)", inline=True)
        embed.add_field(name="🃏 Cartes possédées", value=str(card_count), inline=True)
        embed.add_field(name="⚔️ Bilan", value=f"{user.wins}V / {user.draws}N / {user.losses}D", inline=True)
        embed.add_field(name="👕 Équipe active", value=team.name if team else "—", inline=True)
        embed.add_field(name="🧩 Formation", value=team.formation if team else "—", inline=True)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="daily", description=f"Récupère ta récompense quotidienne de {config.DAILY_REWARD} {config.CURRENCY_SYMBOL}.")
    async def daily(self, interaction: discord.Interaction):
        async with SessionLocal() as session:
            user = await get_or_create_user(session, interaction.user.id)
            remaining = daily_on_cooldown(user)
            if remaining is not None:
                await session.commit()
                await interaction.response.send_message(
                    f"⏳ Tu as déjà récupéré ta récompense. Reviens dans **{format_timedelta(remaining)}**.",
                    ephemeral=True,
                )
                return
            user.currency += config.DAILY_REWARD
            user.last_daily = dt.datetime.utcnow()
            new_balance = user.currency
            await session.commit()

        embed = discord.Embed(
            title="🎁 Récompense quotidienne",
            description=f"Tu as reçu **{config.DAILY_REWARD} {config.CURRENCY_SYMBOL}** !\nNouveau solde : **{new_balance} {config.CURRENCY_SYMBOL}**.",
            color=config.rarity_embed_color(3),
        )
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(ProfileCog(bot))
