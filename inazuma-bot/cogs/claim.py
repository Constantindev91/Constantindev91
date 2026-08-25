from __future__ import annotations

import datetime as dt
import random

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import func, select

import config
from db.database import SessionLocal
from db.models import PlayerTemplate, TechniqueTemplate, User, UserCard
from db.repository import claim_on_cooldown, format_timedelta, get_or_create_user
from utils.card_render import CardData, render_player_card


def _pick_rarity() -> int:
    rarities = list(config.RARITY_WEIGHTS.keys())
    weights = list(config.RARITY_WEIGHTS.values())
    return random.choices(rarities, weights=weights, k=1)[0]


async def _pick_player_template(session, rarity: int) -> PlayerTemplate:
    stmt = select(PlayerTemplate).where(PlayerTemplate.rarity == rarity).order_by(func.random()).limit(1)
    player = await session.scalar(stmt)
    if player is None:
        # Fallback if this rarity happens to have zero entries in data/players.json
        stmt = select(PlayerTemplate).order_by(func.random()).limit(1)
        player = await session.scalar(stmt)
    return player


class KeepSellView(discord.ui.View):
    def __init__(self, author_id: int, card_id: int, player_name: str, rarity: int):
        super().__init__(timeout=config.CLAIM_VIEW_TIMEOUT)
        self.author_id = author_id
        self.card_id = card_id
        self.player_name = player_name
        self.rarity = rarity
        self.resolved = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Ce n'est pas ta carte à réclamer !", ephemeral=True)
            return False
        return True

    async def on_timeout(self) -> None:
        self.resolved = True
        for item in self.children:
            item.disabled = True  # type: ignore[attr-defined]

    @discord.ui.button(label="Garder", style=discord.ButtonStyle.success, emoji="🟢")
    async def keep(self, interaction: discord.Interaction, _: discord.ui.Button):
        self.resolved = True
        for item in self.children:
            item.disabled = True  # type: ignore[attr-defined]
        await interaction.response.edit_message(
            content=f"✅ Tu gardes **{self.player_name}** dans ta collection !", view=self
        )
        self.stop()

    @discord.ui.button(label="Vendre", style=discord.ButtonStyle.danger, emoji="🔴")
    async def sell(self, interaction: discord.Interaction, _: discord.ui.Button):
        self.resolved = True
        for item in self.children:
            item.disabled = True  # type: ignore[attr-defined]
        base = config.sell_value(self.rarity)
        variance = random.randint(-int(base * 0.1), int(base * 0.1))
        value = max(10, base + variance)

        async with SessionLocal() as session:
            card = await session.get(UserCard, self.card_id)
            user = await session.get(User, self.author_id)
            if card is not None and user is not None:
                await session.delete(card)
                user.currency += value
                await session.commit()

        await interaction.response.edit_message(
            content=f"💰 Tu as vendu **{self.player_name}** pour **{value} {config.CURRENCY_SYMBOL}** !",
            view=self,
        )
        self.stop()


class ClaimCog(commands.Cog):
    """Le cœur du bot : réclamer un nouveau joueur toutes les 30 minutes."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="claim", description="Réclame un nouveau joueur Inazuma aléatoire (toutes les 30 min).")
    async def claim(self, interaction: discord.Interaction):
        await interaction.response.defer()

        async with SessionLocal() as session:
            user = await get_or_create_user(session, interaction.user.id)
            remaining = claim_on_cooldown(user)
            if remaining is not None:
                await session.commit()
                await interaction.followup.send(
                    f"⏳ Ton prochain claim est disponible dans **{format_timedelta(remaining)}**.",
                    ephemeral=True,
                )
                return

            rarity = _pick_rarity()
            player = await _pick_player_template(session, rarity)
            if player is None:
                await interaction.followup.send(
                    "⚠️ Aucun joueur n'est encore chargé en base. Contacte l'administrateur du bot.",
                    ephemeral=True,
                )
                return

            technique = None
            if player.signature_technique:
                technique = await session.get(TechniqueTemplate, player.signature_technique)

            card = UserCard(owner_id=user.discord_id, player_id=player.id)
            session.add(card)
            user.last_claim = dt.datetime.utcnow()
            await session.flush()
            card_id = card.id

            card_data = CardData(
                name=player.name,
                name_en=player.name_en,
                position=player.position,
                team_origin=player.team_origin,
                series=player.series,
                element=player.element,
                rarity=player.rarity,
                kick=player.kick,
                pass_=player.pass_,
                defense=player.defense,
                speed=player.speed,
                technique=player.technique,
                overall=player.overall,
                technique_name=technique.name if technique else None,
            )
            await session.commit()

        buf = render_player_card(card_data)
        file = discord.File(buf, filename="card.png")
        embed = discord.Embed(
            title=f"{config.RARITY_STARS[player.rarity]} Nouveau joueur !",
            description=(
                f"**{player.name}** ({player.name_en}) rejoint ta collection !\n"
                f"_{player.flavor}_"
            ),
            color=config.rarity_embed_color(player.rarity),
        )
        embed.set_image(url="attachment://card.png")
        embed.set_footer(text=f"ID de carte : #{card_id} — décide vite, tu as 90 secondes !")

        view = KeepSellView(interaction.user.id, card_id, player.name, player.rarity)
        await interaction.followup.send(embed=embed, file=file, view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(ClaimCog(bot))
