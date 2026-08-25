from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import select
from sqlalchemy.orm import selectinload

import config
from db.database import SessionLocal
from db.models import Team, TeamSlot, TradeOffer, User, UserCard
from db.repository import get_or_create_user
from utils.autocomplete import own_pending_trade_autocomplete


async def _resolve_owned_cards_by_name(session, owner_id: int, raw: str | None) -> tuple[list[UserCard], str | None]:
    """Parses a comma-separated list of player-name fragments into that owner's cards.

    Returns (cards, error_message) — error_message is set (and cards is []) if any
    token doesn't match exactly one owned card.
    """
    if not raw:
        return [], None
    stmt = select(UserCard).where(UserCard.owner_id == owner_id).options(selectinload(UserCard.player))
    owned = list((await session.execute(stmt)).scalars().all())

    resolved: list[UserCard] = []
    for token in [t.strip() for t in raw.split(",") if t.strip()]:
        needle = token.lower()
        matches = [c for c in owned if needle in c.player.name.lower() or needle in c.player.name_en.lower()]
        if not matches:
            return [], f"❌ Aucune carte correspondant à **{token}** n'a été trouvée."
        if len(matches) > 1:
            options = ", ".join(f"{m.player.name_en} (OVR {m.player.overall})" for m in matches[:5])
            return [], f"❌ Plusieurs cartes correspondent à **{token}** : {options}. Précise davantage le nom."
        resolved.append(matches[0])
    return resolved, None


async def _unslot_card(session, card: UserCard) -> None:
    user = await session.get(User, card.owner_id)
    if user is None or user.active_team_id is None:
        return
    team = await session.get(Team, user.active_team_id)
    if team is None:
        return
    slots = list((await session.execute(select(TeamSlot).where(TeamSlot.team_id == team.id, TeamSlot.card_id == card.id))).scalars())
    for s in slots:
        s.card_id = None


class TradeView(discord.ui.View):
    def __init__(self, trade_id: int, from_id: int, to_id: int):
        super().__init__(timeout=600)
        self.trade_id = trade_id
        self.from_id = from_id
        self.to_id = to_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.to_id:
            await interaction.response.send_message("Seul le destinataire de cet échange peut répondre.", ephemeral=True)
            return False
        return True

    async def on_timeout(self) -> None:
        async with SessionLocal() as session:
            trade = await session.get(TradeOffer, self.trade_id)
            if trade and trade.status == "pending":
                trade.status = "expired"
                await session.commit()

    @discord.ui.button(label="Accepter", style=discord.ButtonStyle.success, emoji="🤝")
    async def accept(self, interaction: discord.Interaction, _: discord.ui.Button):
        async with SessionLocal() as session:
            trade = await session.get(TradeOffer, self.trade_id)
            if trade is None or trade.status != "pending":
                await interaction.response.send_message("❌ Cet échange n'est plus valide.", ephemeral=True)
                return

            from_user = await session.get(User, trade.from_user_id)
            to_user = await session.get(User, trade.to_user_id)

            give_cards = [await session.get(UserCard, cid) for cid in trade.offer_card_ids]
            want_cards = [await session.get(UserCard, cid) for cid in trade.request_card_ids]

            if any(c is None or c.owner_id != trade.from_user_id or c.locked for c in give_cards):
                trade.status = "cancelled"
                await session.commit()
                await interaction.response.send_message("❌ L'offre n'est plus valide (carte manquante/verrouillée). Échange annulé.", ephemeral=True)
                return
            if any(c is None or c.owner_id != trade.to_user_id or c.locked for c in want_cards):
                trade.status = "cancelled"
                await session.commit()
                await interaction.response.send_message("❌ Ta partie de l'offre n'est plus valide (carte manquante/verrouillée). Échange annulé.", ephemeral=True)
                return
            if from_user.currency < trade.offer_currency:
                trade.status = "cancelled"
                await session.commit()
                await interaction.response.send_message("❌ L'auteur de l'offre n'a plus assez de KP. Échange annulé.", ephemeral=True)
                return
            if to_user.currency < trade.request_currency:
                await interaction.response.send_message(
                    f"❌ Il te faut **{trade.request_currency} {config.CURRENCY_SYMBOL}** pour accepter.", ephemeral=True
                )
                return

            for c in give_cards:
                await _unslot_card(session, c)
                c.owner_id = trade.to_user_id
                c.equipped_technique_id = None
            for c in want_cards:
                await _unslot_card(session, c)
                c.owner_id = trade.from_user_id
                c.equipped_technique_id = None

            from_user.currency += trade.request_currency - trade.offer_currency
            to_user.currency += trade.offer_currency - trade.request_currency

            trade.status = "accepted"
            await session.commit()

        for item in self.children:
            item.disabled = True  # type: ignore[attr-defined]
        await interaction.response.edit_message(content="✅ Échange conclu !", view=self)
        self.stop()

    @discord.ui.button(label="Refuser", style=discord.ButtonStyle.danger, emoji="🚫")
    async def decline(self, interaction: discord.Interaction, _: discord.ui.Button):
        async with SessionLocal() as session:
            trade = await session.get(TradeOffer, self.trade_id)
            if trade and trade.status == "pending":
                trade.status = "declined"
                await session.commit()
        for item in self.children:
            item.disabled = True  # type: ignore[attr-defined]
        await interaction.response.edit_message(content="🚫 Échange refusé.", view=self)
        self.stop()


class TradeCog(commands.Cog):
    """Échanges directs de cartes/KP entre deux membres du serveur."""

    trade_group = app_commands.Group(name="trade", description="Propose un échange à un autre membre")

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @trade_group.command(name="propose", description="Propose un échange de cartes/KP à un autre membre.")
    @app_commands.describe(
        member="Le membre à qui proposer l'échange",
        give_cards="Tes cartes offertes : noms séparés par des virgules (ex: mark, gouenji)",
        give_currency=f"Les {config.CURRENCY_SYMBOL} que tu offres en plus",
        want_cards="Les cartes que tu demandes en retour : noms séparés par des virgules",
        want_currency=f"Les {config.CURRENCY_SYMBOL} que tu demandes en retour",
    )
    @app_commands.rename(give_cards="tes_joueurs", give_currency="tes_kp", want_cards="joueurs_demandés", want_currency="kp_demandés")
    async def propose(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        give_cards: str | None = None,
        give_currency: app_commands.Range[int, 0, None] = 0,
        want_cards: str | None = None,
        want_currency: app_commands.Range[int, 0, None] = 0,
    ):
        if member.id == interaction.user.id:
            await interaction.response.send_message("❌ Tu ne peux pas t'échanger avec toi-même.", ephemeral=True)
            return
        if member.bot:
            await interaction.response.send_message("❌ Impossible d'échanger avec un bot.", ephemeral=True)
            return

        async with SessionLocal() as session:
            await get_or_create_user(session, interaction.user.id)
            await get_or_create_user(session, member.id)

            give_cards_resolved, error = await _resolve_owned_cards_by_name(session, interaction.user.id, give_cards)
            if error:
                await interaction.response.send_message(error, ephemeral=True)
                return
            locked = [c for c in give_cards_resolved if c.locked]
            if locked:
                await interaction.response.send_message(f"🔒 **{locked[0].player.name_en}** est verrouillé — déverrouille-le avec `/unlock`.", ephemeral=True)
                return

            want_cards_resolved, error = await _resolve_owned_cards_by_name(session, member.id, want_cards)
            if error:
                await interaction.response.send_message(error.replace("carte correspondant", f"carte de {member.display_name} correspondant"), ephemeral=True)
                return

            if not give_cards_resolved and not give_currency:
                await interaction.response.send_message("❌ Tu dois offrir au moins une carte ou des KP.", ephemeral=True)
                return

            give_ids = [c.id for c in give_cards_resolved]
            want_ids = [c.id for c in want_cards_resolved]
            give_names = [c.player.name_en for c in give_cards_resolved]
            want_names = [c.player.name_en for c in want_cards_resolved]

            trade = TradeOffer(
                from_user_id=interaction.user.id,
                to_user_id=member.id,
                offer_card_ids=give_ids,
                offer_currency=give_currency,
                request_card_ids=want_ids,
                request_currency=want_currency,
            )
            session.add(trade)
            await session.commit()
            trade_id = trade.id

        embed = discord.Embed(
            title="🔄 Proposition d'échange",
            description=f"{interaction.user.mention} propose un échange à {member.mention} !",
            color=config.rarity_embed_color(4),
        )
        offer_lines = give_names + ([f"{give_currency} {config.CURRENCY_SYMBOL}"] if give_currency else [])
        request_lines = want_names + ([f"{want_currency} {config.CURRENCY_SYMBOL}"] if want_currency else [])
        embed.add_field(name=f"📤 {interaction.user.display_name} offre", value="\n".join(offer_lines) or "Rien", inline=True)
        embed.add_field(name=f"📥 {member.display_name} donne", value="\n".join(request_lines) or "Rien", inline=True)
        embed.set_footer(text="Expire dans 10 minutes")

        view = TradeView(trade_id, interaction.user.id, member.id)
        await interaction.response.send_message(content=member.mention, embed=embed, view=view)

    @trade_group.command(name="cancel", description="Annule un échange que tu as proposé et qui est encore en attente.")
    @app_commands.describe(trade_id="Choisis l'échange à annuler (par destinataire)")
    @app_commands.rename(trade_id="échange")
    @app_commands.autocomplete(trade_id=own_pending_trade_autocomplete)
    async def cancel(self, interaction: discord.Interaction, trade_id: int):
        async with SessionLocal() as session:
            trade = await session.get(TradeOffer, trade_id)
            if trade is None or trade.from_user_id != interaction.user.id or trade.status != "pending":
                await interaction.response.send_message("❌ Échange introuvable ou déjà réglé — choisis dans la liste proposée.", ephemeral=True)
                return
            trade.status = "cancelled"
            await session.commit()
        await interaction.response.send_message("✅ Échange annulé.")


async def setup(bot: commands.Bot):
    await bot.add_cog(TradeCog(bot))
