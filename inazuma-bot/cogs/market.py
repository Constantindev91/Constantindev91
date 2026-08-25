from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import select
from sqlalchemy.orm import selectinload

import config
from db.database import SessionLocal
from db.models import MarketListing, PlayerTemplate, Team, TeamSlot, User, UserCard
from db.repository import get_or_create_user
from utils.pagination import Paginator, chunk

POSITION_EMOJI = {"GK": "🧤", "DF": "🛡️", "MF": "🎯", "FW": "⚡"}


class MarketCog(commands.Cog):
    """Marché des transferts : mets tes joueurs en vente pour les autres membres du serveur."""

    market_group = app_commands.Group(name="market", description="Le marché des transferts entre joueurs")

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @market_group.command(name="list", description="Met une carte en vente sur le marché des transferts.")
    @app_commands.describe(card_id="ID de la carte (#...)", price=f"Prix demandé en {config.CURRENCY_SYMBOL}")
    async def list_card(self, interaction: discord.Interaction, card_id: int, price: app_commands.Range[int, config.MARKET_MIN_PRICE, config.MARKET_MAX_PRICE]):
        async with SessionLocal() as session:
            card = await session.get(UserCard, card_id, options=[selectinload(UserCard.player)])
            if card is None or card.owner_id != interaction.user.id:
                await interaction.response.send_message("❌ Cette carte ne t'appartient pas.", ephemeral=True)
                return
            if card.locked:
                await interaction.response.send_message("🔒 Déverrouille d'abord cette carte avec `/unlock`.", ephemeral=True)
                return
            existing = await session.scalar(
                select(MarketListing).where(MarketListing.card_id == card.id, MarketListing.active == True)  # noqa: E712
            )
            if existing is not None:
                await interaction.response.send_message("❌ Cette carte est déjà en vente.", ephemeral=True)
                return

            # Pull the card out of the lineup/bench if it was placed in the active team.
            team = await session.get(Team, (await session.get(User, interaction.user.id)).active_team_id)
            if team is not None:
                slots = list((await session.execute(select(TeamSlot).where(TeamSlot.team_id == team.id, TeamSlot.card_id == card.id))).scalars())
                for s in slots:
                    s.card_id = None

            listing = MarketListing(seller_id=interaction.user.id, card_id=card.id, price=price)
            session.add(listing)
            await session.commit()
            listing_id = listing.id
            name = card.player.name

        await interaction.response.send_message(
            f"📢 **{name}** mis en vente pour **{price} {config.CURRENCY_SYMBOL}** (annonce `#{listing_id}`)."
        )

    @market_group.command(name="cancel", description="Annule une de tes annonces sur le marché.")
    async def cancel(self, interaction: discord.Interaction, listing_id: int):
        async with SessionLocal() as session:
            listing = await session.get(MarketListing, listing_id)
            if listing is None or not listing.active or listing.seller_id != interaction.user.id:
                await interaction.response.send_message("❌ Annonce introuvable.", ephemeral=True)
                return
            listing.active = False
            await session.commit()
        await interaction.response.send_message(f"✅ Annonce `#{listing_id}` annulée, la carte reste dans ta collection.")

    @market_group.command(name="buy", description="Achète une carte listée sur le marché des transferts.")
    async def buy(self, interaction: discord.Interaction, listing_id: int):
        async with SessionLocal() as session:
            listing = await session.get(MarketListing, listing_id, options=[selectinload(MarketListing.card).selectinload(UserCard.player)])
            if listing is None or not listing.active:
                await interaction.response.send_message("❌ Annonce introuvable ou déjà vendue.", ephemeral=True)
                return
            if listing.seller_id == interaction.user.id:
                await interaction.response.send_message("❌ Tu ne peux pas acheter ta propre carte.", ephemeral=True)
                return

            buyer = await get_or_create_user(session, interaction.user.id)
            if buyer.currency < listing.price:
                await interaction.response.send_message(
                    f"❌ Il te faut **{listing.price} {config.CURRENCY_SYMBOL}** (tu as {buyer.currency}).", ephemeral=True
                )
                return

            seller = await session.get(User, listing.seller_id)
            card = listing.card
            seller_proceeds = round(listing.price * (1 - config.MARKET_TAX_RATE))

            buyer.currency -= listing.price
            seller.currency += seller_proceeds
            card.owner_id = buyer.discord_id
            card.equipped_technique_id = None
            card.locked = False
            listing.active = False
            await session.commit()

            name = card.player.name
            rarity = card.player.rarity

        embed = discord.Embed(
            title="✅ Transfert conclu !",
            description=(
                f"<@{interaction.user.id}> a recruté **{name}** {config.RARITY_STARS[rarity]} "
                f"pour **{listing.price} {config.CURRENCY_SYMBOL}** (le vendeur touche {seller_proceeds} après taxe)."
            ),
            color=config.rarity_embed_color(rarity),
        )
        await interaction.response.send_message(embed=embed)

    @market_group.command(name="browse", description="Parcourt les annonces actives du marché des transferts.")
    @app_commands.describe(position="Filtrer par poste", max_price="Prix maximum")
    @app_commands.choices(position=[
        app_commands.Choice(name="Gardien", value="GK"),
        app_commands.Choice(name="Défenseur", value="DF"),
        app_commands.Choice(name="Milieu", value="MF"),
        app_commands.Choice(name="Attaquant", value="FW"),
    ])
    async def browse(self, interaction: discord.Interaction, position: app_commands.Choice[str] | None = None, max_price: int | None = None):
        async with SessionLocal() as session:
            stmt = (
                select(MarketListing)
                .where(MarketListing.active == True)  # noqa: E712
                .options(selectinload(MarketListing.card).selectinload(UserCard.player))
                .join(UserCard, MarketListing.card_id == UserCard.id)
                .join(PlayerTemplate, UserCard.player_id == PlayerTemplate.id)
                .order_by(MarketListing.price.asc())
            )
            if position:
                stmt = stmt.where(PlayerTemplate.position == position.value)
            if max_price:
                stmt = stmt.where(MarketListing.price <= max_price)
            listings = list((await session.execute(stmt)).scalars().all())

        if not listings:
            await interaction.response.send_message("📭 Aucune annonce ne correspond à ces critères.", ephemeral=True)
            return

        pages = []
        for group in chunk(listings, 10):
            lines = [
                f"`#{l.id}` {POSITION_EMOJI.get(l.card.player.position,'')} {config.RARITY_STARS[l.card.player.rarity]} "
                f"**{l.card.player.name}** (OVR {l.card.player.overall}) — **{l.price} {config.CURRENCY_SYMBOL}** — vendeur <@{l.seller_id}>"
                for l in group
            ]
            embed = discord.Embed(title="🏦 Marché des transferts", description="\n".join(lines), color=config.rarity_embed_color(4))
            embed.set_footer(text="Achète avec /market buy <id>")
            pages.append(embed)
        await interaction.response.send_message(embed=pages[0], view=Paginator(interaction.user.id, pages))

    @market_group.command(name="mine", description="Affiche tes annonces actives sur le marché.")
    async def mine(self, interaction: discord.Interaction):
        async with SessionLocal() as session:
            stmt = (
                select(MarketListing)
                .where(MarketListing.active == True, MarketListing.seller_id == interaction.user.id)  # noqa: E712
                .options(selectinload(MarketListing.card).selectinload(UserCard.player))
            )
            listings = list((await session.execute(stmt)).scalars().all())

        if not listings:
            await interaction.response.send_message("Tu n'as aucune annonce active.", ephemeral=True)
            return

        lines = [f"`#{l.id}` **{l.card.player.name}** — {l.price} {config.CURRENCY_SYMBOL}" for l in listings]
        embed = discord.Embed(title="📋 Mes annonces", description="\n".join(lines), color=config.rarity_embed_color(3))
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(MarketCog(bot))
