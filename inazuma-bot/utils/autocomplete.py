"""Shared name-based autocomplete callbacks.

Every "pick a card/technique/tactic/coach/listing" parameter in the bot
uses one of these so players never have to type an exact id — they type
a first name or partial name (e.g. "mark") and Discord shows matching
picks. Choice labels lead with the western/French dub name since that's
what players actually search for.
"""
from __future__ import annotations

import discord
from discord import app_commands
from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload

import config
from db.database import SessionLocal
from db.models import (
    CoachTemplate,
    MarketListing,
    PlayerTemplate,
    TacticTemplate,
    TechniqueTemplate,
    TradeOffer,
    UserCard,
    UserCoach,
    UserTactic,
    UserTechnique,
)


def _name_filter(model, current: str):
    like = f"%{current.lower()}%"
    return or_(func.lower(model.name).like(like), func.lower(getattr(model, "name_en", model.name)).like(like))


async def owned_card_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[int]]:
    """For 'card_id' params: cards the invoking user owns, searchable by player name."""
    async with SessionLocal() as session:
        stmt = (
            select(UserCard)
            .where(UserCard.owner_id == interaction.user.id)
            .options(selectinload(UserCard.player))
            .join(PlayerTemplate)
        )
        if current:
            stmt = stmt.where(_name_filter(PlayerTemplate, current))
        stmt = stmt.order_by(PlayerTemplate.rarity.desc(), PlayerTemplate.name_en).limit(25)
        cards = list((await session.execute(stmt)).scalars().all())
    return [
        app_commands.Choice(
            name=f"{c.player.name_en} ({c.player.name}) {config.RARITY_STARS[c.player.rarity]} OVR{c.player.overall}"[:100],
            value=c.id,
        )
        for c in cards
    ]


async def any_player_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    """For direct player purchase: searches the full 300-player roster by name."""
    async with SessionLocal() as session:
        stmt = select(PlayerTemplate)
        if current:
            stmt = stmt.where(_name_filter(PlayerTemplate, current))
        stmt = stmt.order_by(PlayerTemplate.rarity.desc(), PlayerTemplate.name_en).limit(25)
        players = list((await session.execute(stmt)).scalars().all())
    return [
        app_commands.Choice(
            name=f"{p.name_en} ({p.name}) {config.RARITY_STARS[p.rarity]} — {p.base_price} {config.CURRENCY_SYMBOL}"[:100],
            value=p.id,
        )
        for p in players
    ]


def _template_autocomplete(model):
    async def _autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        async with SessionLocal() as session:
            stmt = select(model)
            if current:
                stmt = stmt.where(func.lower(model.name).like(f"%{current.lower()}%"))
            stmt = stmt.order_by(model.rarity.desc(), model.name).limit(25)
            rows = list((await session.execute(stmt)).scalars().all())
        return [app_commands.Choice(name=f"{r.name} {config.RARITY_STARS[r.rarity]}"[:100], value=r.id) for r in rows]

    return _autocomplete


technique_autocomplete = _template_autocomplete(TechniqueTemplate)
tactic_autocomplete = _template_autocomplete(TacticTemplate)
coach_autocomplete = _template_autocomplete(CoachTemplate)


def _owned_item_autocomplete(model, template_relation: str, template_model):
    async def _autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[int]]:
        async with SessionLocal() as session:
            stmt = (
                select(model)
                .where(model.owner_id == interaction.user.id)
                .options(selectinload(getattr(model, template_relation)))
            )
            rows = list((await session.execute(stmt)).scalars().all())
        cur = current.lower()
        out = []
        for r in rows:
            template = getattr(r, template_relation)
            if cur and cur not in template.name.lower():
                continue
            out.append(app_commands.Choice(name=f"{template.name} {config.RARITY_STARS[template.rarity]}"[:100], value=r.id))
        return out[:25]

    return _autocomplete


owned_technique_autocomplete = _owned_item_autocomplete(UserTechnique, "technique", TechniqueTemplate)
owned_tactic_autocomplete = _owned_item_autocomplete(UserTactic, "tactic", TacticTemplate)
owned_coach_autocomplete = _owned_item_autocomplete(UserCoach, "coach", CoachTemplate)


async def _listing_choices(interaction: discord.Interaction, current: str, *, own_only: bool) -> list[app_commands.Choice[int]]:
    async with SessionLocal() as session:
        stmt = (
            select(MarketListing)
            .where(MarketListing.active == True)  # noqa: E712
            .options(selectinload(MarketListing.card).selectinload(UserCard.player))
            .join(UserCard, MarketListing.card_id == UserCard.id)
            .join(PlayerTemplate, UserCard.player_id == PlayerTemplate.id)
        )
        if own_only:
            stmt = stmt.where(MarketListing.seller_id == interaction.user.id)
        if current:
            stmt = stmt.where(_name_filter(PlayerTemplate, current))
        stmt = stmt.order_by(MarketListing.price.asc()).limit(25)
        listings = list((await session.execute(stmt)).scalars().all())

    choices = []
    for listing in listings:
        seller = interaction.guild.get_member(listing.seller_id) if interaction.guild else None
        seller_name = seller.display_name if seller else "vendeur inconnu"
        p = listing.card.player
        label = f"{p.name_en} {config.RARITY_STARS[p.rarity]} — {listing.price} {config.CURRENCY_SYMBOL}"
        if not own_only:
            label += f" (par {seller_name})"
        choices.append(app_commands.Choice(name=label[:100], value=listing.id))
    return choices


async def market_listing_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[int]]:
    """For '/market buy': every active listing on the server, searchable by player name."""
    return await _listing_choices(interaction, current, own_only=False)


async def own_listing_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[int]]:
    """For '/market cancel': only the invoking user's own active listings."""
    return await _listing_choices(interaction, current, own_only=True)


async def own_pending_trade_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[int]]:
    """For '/trade cancel': the invoking user's own pending trade proposals, labeled by recipient."""
    async with SessionLocal() as session:
        stmt = select(TradeOffer).where(TradeOffer.from_user_id == interaction.user.id, TradeOffer.status == "pending")
        rows = list((await session.execute(stmt)).scalars().all())

    choices = []
    for t in rows:
        recipient = interaction.guild.get_member(t.to_user_id) if interaction.guild else None
        rname = recipient.display_name if recipient else "un membre"
        if current and current.lower() not in rname.lower():
            continue
        label = f"Vers {rname} — {len(t.offer_card_ids)} carte(s) + {t.offer_currency} {config.CURRENCY_SYMBOL}"
        choices.append(app_commands.Choice(name=label[:100], value=t.id))
    return choices[:25]
