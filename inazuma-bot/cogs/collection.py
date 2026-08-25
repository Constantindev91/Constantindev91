from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import select
from sqlalchemy.orm import selectinload

import config
from db.database import SessionLocal
from db.models import PlayerTemplate, TechniqueTemplate, User, UserCard, UserTechnique
from db.repository import get_or_create_user
from utils.autocomplete import any_player_autocomplete, owned_card_autocomplete
from utils.card_render import CardData, render_player_card
from utils.pagination import Paginator, chunk

POSITION_EMOJI = {"GK": "🧤", "DF": "🛡️", "MF": "🎯", "FW": "⚡"}


def _player_image(embed: discord.Embed, template, technique_name: str | None) -> discord.File | None:
    """Uses template.image_url if a server admin set one, otherwise renders a card."""
    if template.image_url:
        embed.set_image(url=template.image_url)
        return None
    card_data = CardData(
        name=template.name, name_en=template.name_en, position=template.position, team_origin=template.team_origin,
        series=template.series, element=template.element, rarity=template.rarity, kick=template.kick,
        pass_=template.pass_, defense=template.defense, speed=template.speed, technique=template.technique,
        overall=template.overall, base_price=template.base_price, player_id=template.id,
        technique_name=technique_name,
    )
    buf = render_player_card(card_data)
    file = discord.File(buf, filename="card.png")
    embed.set_image(url="attachment://card.png")
    return file


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
                .order_by(PlayerTemplate.rarity.desc(), PlayerTemplate.name_en)
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
                    f"{POSITION_EMOJI.get(p.position,'')} {config.RARITY_STARS[p.rarity]} ({p.rarity}/5) "
                    f"**{p.name_en}** ({p.position}) — OVR {p.overall} · {p.base_price} {config.CURRENCY_SYMBOL} {lock}"
                )
            embed = discord.Embed(
                title=f"🃏 Collection de {target.display_name} ({len(cards)} joueurs)",
                description="\n".join(lines),
                color=config.rarity_embed_color(3),
            )
            pages.append(embed)

        await interaction.response.send_message(embed=pages[0], view=Paginator(interaction.user.id, pages))

    @app_commands.command(name="buy", description="Achète directement un joueur au prix de base — cherche par nom (ex: mark, gouenji...).")
    @app_commands.describe(joueur="Tape un bout du nom du joueur, choisis dans la liste proposée")
    @app_commands.autocomplete(joueur=any_player_autocomplete)
    async def buy(self, interaction: discord.Interaction, joueur: str):
        async with SessionLocal() as session:
            template = await session.get(PlayerTemplate, joueur)
            if template is None:
                await interaction.response.send_message(
                    "❌ Joueur introuvable — tape un bout de son nom et choisis une suggestion dans la liste.",
                    ephemeral=True,
                )
                return

            user = await get_or_create_user(session, interaction.user.id)
            if user.currency < template.base_price:
                await interaction.response.send_message(
                    f"❌ Il te faut **{template.base_price} {config.CURRENCY_SYMBOL}** pour recruter **{template.name_en}** "
                    f"(tu as {user.currency}).",
                    ephemeral=True,
                )
                return

            technique = None
            if template.signature_technique:
                technique = await session.get(TechniqueTemplate, template.signature_technique)

            user.currency -= template.base_price
            card = UserCard(owner_id=user.discord_id, player_id=template.id)
            session.add(card)
            await session.flush()

            embed = discord.Embed(
                title=f"✅ Recrutement réussi ! {config.RARITY_STARS[template.rarity]} ({template.rarity}/5)",
                description=(
                    f"**{template.name_en}** ({template.name}) rejoint ta collection pour "
                    f"**{template.base_price} {config.CURRENCY_SYMBOL}** !\n_{template.flavor}_"
                ),
                color=config.rarity_embed_color(template.rarity),
            )
            file = _player_image(embed, template, technique.name if technique else None)
            await session.commit()

        kwargs = {"file": file} if file is not None else {}
        await interaction.response.send_message(embed=embed, **kwargs)

    @app_commands.command(name="card", description="Affiche la carte détaillée d'un joueur de ta collection.")
    @app_commands.describe(card_id="Tape le nom du joueur pour retrouver sa carte")
    @app_commands.rename(card_id="joueur")
    @app_commands.autocomplete(card_id=owned_card_autocomplete)
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
            owner_id = card.owner_id
            resale = config.player_sell_value(p.base_price)
            embed = discord.Embed(
                title=f"{config.RARITY_STARS[p.rarity]} {p.name_en} ({p.rarity}/5)",
                description=(
                    f"_{p.flavor}_\nPropriétaire : <@{owner_id}>\n"
                    f"💰 Valeur : **{p.base_price} {config.CURRENCY_SYMBOL}** (revente : {resale} {config.CURRENCY_SYMBOL})"
                ),
                color=config.rarity_embed_color(p.rarity),
            )
            file = _player_image(embed, p, technique.name if technique else None)

        kwargs = {"file": file} if file is not None else {}
        await interaction.response.send_message(embed=embed, **kwargs)

    @app_commands.command(name="sell", description="Vend définitivement une carte de ta collection contre des KP (40% du prix de base).")
    @app_commands.describe(card_id="Tape le nom du joueur à vendre, choisis dans la liste proposée")
    @app_commands.rename(card_id="joueur")
    @app_commands.autocomplete(card_id=owned_card_autocomplete)
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
            value = config.player_sell_value(card.player.base_price)
            name = card.player.name_en

            user = await session.get(User, interaction.user.id)
            user.currency += value
            await session.delete(card)
            await session.commit()

        await interaction.response.send_message(
            f"💰 Tu as vendu **{name}** pour **{value} {config.CURRENCY_SYMBOL}**."
        )

    @app_commands.command(name="lock", description="Verrouille une carte pour éviter de la vendre/échanger par erreur.")
    @app_commands.describe(card_id="Tape le nom du joueur")
    @app_commands.rename(card_id="joueur")
    @app_commands.autocomplete(card_id=owned_card_autocomplete)
    async def lock(self, interaction: discord.Interaction, card_id: int):
        await self._set_lock(interaction, card_id, True)

    @app_commands.command(name="unlock", description="Déverrouille une carte.")
    @app_commands.describe(card_id="Tape le nom du joueur")
    @app_commands.rename(card_id="joueur")
    @app_commands.autocomplete(card_id=owned_card_autocomplete)
    async def unlock(self, interaction: discord.Interaction, card_id: int):
        await self._set_lock(interaction, card_id, False)

    async def _set_lock(self, interaction: discord.Interaction, card_id: int, locked: bool):
        async with SessionLocal() as session:
            card = await session.get(UserCard, card_id, options=[selectinload(UserCard.player)])
            if card is None or card.owner_id != interaction.user.id:
                await interaction.response.send_message("❌ Cette carte ne t'appartient pas.", ephemeral=True)
                return
            card.locked = locked
            name = card.player.name_en
            await session.commit()
        state = "verrouillée 🔒" if locked else "déverrouillée 🔓"
        await interaction.response.send_message(f"**{name}** {state}.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(CollectionCog(bot))
