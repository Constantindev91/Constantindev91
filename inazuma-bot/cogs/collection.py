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
                    f"`#{c.id}` {POSITION_EMOJI.get(p.position,'')} {config.RARITY_STARS[p.rarity]} ({p.rarity}/5) "
                    f"**{p.name}** ({p.position}) — OVR {p.overall} · {p.base_price} {config.CURRENCY_SYMBOL} {lock}"
                )
            embed = discord.Embed(
                title=f"🃏 Collection de {target.display_name} ({len(cards)} joueurs)",
                description="\n".join(lines),
                color=config.rarity_embed_color(3),
            )
            pages.append(embed)

        await interaction.response.send_message(embed=pages[0], view=Paginator(interaction.user.id, pages))

    @app_commands.command(name="buy", description="Achète directement un joueur au prix de base — cherche par nom (ex: mark, gouenji...).")
    @app_commands.describe(player="Tape un bout du nom du joueur, choisis dans la liste proposée")
    @app_commands.autocomplete(player=any_player_autocomplete)
    async def buy(self, interaction: discord.Interaction, player: str):
        async with SessionLocal() as session:
            template = await session.get(PlayerTemplate, player)
            if template is None:
                await interaction.response.send_message(
                    "❌ Joueur introuvable — tape un bout de son nom et choisis une suggestion dans la liste.",
                    ephemeral=True,
                )
                return

            user = await get_or_create_user(session, interaction.user.id)
            if user.currency < template.base_price:
                await interaction.response.send_message(
                    f"❌ Il te faut **{template.base_price} {config.CURRENCY_SYMBOL}** pour recruter **{template.name}** "
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
            card_id = card.id

            card_data = CardData(
                name=template.name, name_en=template.name_en, position=template.position, team_origin=template.team_origin,
                series=template.series, element=template.element, rarity=template.rarity, kick=template.kick,
                pass_=template.pass_, defense=template.defense, speed=template.speed, technique=template.technique,
                overall=template.overall, base_price=template.base_price, player_id=template.id,
                technique_name=technique.name if technique else None,
            )
            flavor, rarity, name, base_price = template.flavor, template.rarity, template.name, template.base_price
            await session.commit()

        buf = render_player_card(card_data)
        file = discord.File(buf, filename="card.png")
        embed = discord.Embed(
            title=f"✅ Recrutement réussi ! {config.RARITY_STARS[rarity]} ({rarity}/5)",
            description=f"**{name}** rejoint ta collection pour **{base_price} {config.CURRENCY_SYMBOL}** !\n_{flavor}_",
            color=config.rarity_embed_color(rarity),
        )
        embed.set_image(url="attachment://card.png")
        embed.set_footer(text=f"ID de carte : #{card_id}")
        await interaction.response.send_message(embed=embed, file=file)

    @app_commands.command(name="card", description="Affiche la carte détaillée d'un joueur de ta collection.")
    @app_commands.describe(card_id="Tape le nom du joueur pour retrouver sa carte")
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
            card_data = CardData(
                name=p.name, name_en=p.name_en, position=p.position, team_origin=p.team_origin,
                series=p.series, element=p.element, rarity=p.rarity, kick=p.kick, pass_=p.pass_,
                defense=p.defense, speed=p.speed, technique=p.technique, overall=p.overall,
                base_price=p.base_price, player_id=p.id,
                technique_name=technique.name if technique else None,
            )
            owner_id = card.owner_id

        buf = render_player_card(card_data)
        file = discord.File(buf, filename="card.png")
        resale = config.player_sell_value(p.base_price)
        embed = discord.Embed(
            title=f"{config.RARITY_STARS[p.rarity]} {p.name} ({p.rarity}/5)",
            description=(
                f"_{p.flavor}_\nPropriétaire : <@{owner_id}>\n"
                f"💰 Valeur : **{p.base_price} {config.CURRENCY_SYMBOL}** (revente : {resale} {config.CURRENCY_SYMBOL})"
            ),
            color=config.rarity_embed_color(p.rarity),
        )
        embed.set_image(url="attachment://card.png")
        await interaction.response.send_message(embed=embed, file=file)

    @app_commands.command(name="sell", description="Vend définitivement une carte de ta collection contre des KP (40% du prix de base).")
    @app_commands.describe(card_id="Tape le nom du joueur à vendre, choisis dans la liste proposée")
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
            name = card.player.name

            user = await session.get(User, interaction.user.id)
            user.currency += value
            await session.delete(card)
            await session.commit()

        await interaction.response.send_message(
            f"💰 Tu as vendu **{name}** pour **{value} {config.CURRENCY_SYMBOL}**."
        )

    @app_commands.command(name="lock", description="Verrouille une carte pour éviter de la vendre/échanger par erreur.")
    @app_commands.autocomplete(card_id=owned_card_autocomplete)
    async def lock(self, interaction: discord.Interaction, card_id: int):
        await self._set_lock(interaction, card_id, True)

    @app_commands.command(name="unlock", description="Déverrouille une carte.")
    @app_commands.autocomplete(card_id=owned_card_autocomplete)
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
