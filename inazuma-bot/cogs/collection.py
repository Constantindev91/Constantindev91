from __future__ import annotations

import random

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import select
from sqlalchemy.orm import selectinload

import config
from db.database import SessionLocal
from db.models import PlayerTemplate, TechniqueTemplate, User, UserCard, UserTechnique
from db.repository import get_or_create_user
from utils.card_render import CardData, render_player_card
from utils.pagination import Paginator, chunk

POSITION_EMOJI = {"GK": "🧤", "DF": "🛡️", "MF": "🎯", "FW": "⚡"}


class CollectionCog(commands.Cog):
    """Consulter, visualiser et vendre les cartes de ta collection."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="collection", description="Affiche la liste de tes joueurs Inazuma.")
    @app_commands.describe(member="Membre à consulter (optionnel)", position="Filtrer par poste", rarity="Filtrer par rareté (1-5)")
    @app_commands.choices(position=[
        app_commands.Choice(name="Gardien", value="GK"),
        app_commands.Choice(name="Défenseur", value="DF"),
        app_commands.Choice(name="Milieu", value="MF"),
        app_commands.Choice(name="Attaquant", value="FW"),
    ])
    async def collection(
        self,
        interaction: discord.Interaction,
        member: discord.Member | None = None,
        position: app_commands.Choice[str] | None = None,
        rarity: app_commands.Range[int, 1, 5] | None = None,
    ):
        target = member or interaction.user
        async with SessionLocal() as session:
            await get_or_create_user(session, target.id)
            stmt = (
                select(UserCard)
                .where(UserCard.owner_id == target.id)
                .options(selectinload(UserCard.player))
                .join(PlayerTemplate)
                .order_by(PlayerTemplate.rarity.desc(), PlayerTemplate.name)
            )
            if position:
                stmt = stmt.where(PlayerTemplate.position == position.value)
            if rarity:
                stmt = stmt.where(PlayerTemplate.rarity == rarity)
            cards = list((await session.execute(stmt)).scalars().all())

        if not cards:
            await interaction.response.send_message(
                f"{'Tu n' if target == interaction.user else target.display_name + ' n'}'as aucune carte pour le moment. Utilise `/claim` !",
                ephemeral=(target == interaction.user),
            )
            return

        pages = []
        for group in chunk(cards, 10):
            lines = []
            for c in group:
                p = c.player
                lock = "🔒 " if c.locked else ""
                lines.append(
                    f"`#{c.id}` {POSITION_EMOJI.get(p.position,'')} {config.RARITY_STARS[p.rarity]} "
                    f"**{p.name}** ({p.position}) — OVR {p.overall} {lock}"
                )
            embed = discord.Embed(
                title=f"🃏 Collection de {target.display_name} ({len(cards)} joueurs)",
                description="\n".join(lines),
                color=config.rarity_embed_color(3),
            )
            pages.append(embed)

        await interaction.response.send_message(embed=pages[0], view=Paginator(interaction.user.id, pages))

    @app_commands.command(name="card", description="Affiche la carte détaillée d'un joueur de ta collection.")
    @app_commands.describe(card_id="L'identifiant #ID de la carte (voir /collection)")
    async def card(self, interaction: discord.Interaction, card_id: int):
        async with SessionLocal() as session:
            card = await session.get(UserCard, card_id, options=[selectinload(UserCard.player)])
            if card is None:
                await interaction.response.send_message("❌ Carte introuvable.", ephemeral=True)
                return
            technique = None
            if card.equipped_technique_id:
                ut = await session.get(UserTechnique, card.equipped_technique_id)
                if ut:
                    technique = await session.get(TechniqueTemplate, ut.technique_id)
            elif card.player.signature_technique:
                technique = await session.get(TechniqueTemplate, card.player.signature_technique)

            p = card.player
            card_data = CardData(
                name=p.name, name_en=p.name_en, position=p.position, team_origin=p.team_origin,
                series=p.series, element=p.element, rarity=p.rarity, kick=p.kick, pass_=p.pass_,
                defense=p.defense, speed=p.speed, technique=p.technique, overall=p.overall,
                technique_name=technique.name if technique else None,
            )
            owner_id = card.owner_id

        buf = render_player_card(card_data)
        file = discord.File(buf, filename="card.png")
        embed = discord.Embed(
            title=f"{config.RARITY_STARS[p.rarity]} {p.name}",
            description=f"_{p.flavor}_\nPropriétaire : <@{owner_id}>",
            color=config.rarity_embed_color(p.rarity),
        )
        embed.set_image(url="attachment://card.png")
        await interaction.response.send_message(embed=embed, file=file)

    @app_commands.command(name="sell", description="Vend définitivement une carte de ta collection contre des KP.")
    @app_commands.describe(card_id="L'identifiant #ID de la carte à vendre")
    async def sell(self, interaction: discord.Interaction, card_id: int):
        async with SessionLocal() as session:
            card = await session.get(UserCard, card_id, options=[selectinload(UserCard.player)])
            if card is None or card.owner_id != interaction.user.id:
                await interaction.response.send_message("❌ Cette carte ne t'appartient pas.", ephemeral=True)
                return
            if card.locked:
                await interaction.response.send_message(
                    "🔒 Cette carte est verrouillée. Utilise `/unlock` avant de la vendre.", ephemeral=True
                )
                return
            base = config.sell_value(card.player.rarity)
            variance = random.randint(-int(base * 0.1), int(base * 0.1))
            value = max(10, base + variance)
            name = card.player.name

            user = await session.get(User, interaction.user.id)
            user.currency += value
            await session.delete(card)
            await session.commit()

        await interaction.response.send_message(
            f"💰 Tu as vendu **{name}** pour **{value} {config.CURRENCY_SYMBOL}**."
        )

    @app_commands.command(name="lock", description="Verrouille une carte pour éviter de la vendre/échanger par erreur.")
    async def lock(self, interaction: discord.Interaction, card_id: int):
        await self._set_lock(interaction, card_id, True)

    @app_commands.command(name="unlock", description="Déverrouille une carte.")
    async def unlock(self, interaction: discord.Interaction, card_id: int):
        await self._set_lock(interaction, card_id, False)

    async def _set_lock(self, interaction: discord.Interaction, card_id: int, locked: bool):
        async with SessionLocal() as session:
            card = await session.get(UserCard, card_id)
            if card is None or card.owner_id != interaction.user.id:
                await interaction.response.send_message("❌ Cette carte ne t'appartient pas.", ephemeral=True)
                return
            card.locked = locked
            await session.commit()
        state = "verrouillée 🔒" if locked else "déverrouillée 🔓"
        await interaction.response.send_message(f"Carte `#{card_id}` {state}.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(CollectionCog(bot))
