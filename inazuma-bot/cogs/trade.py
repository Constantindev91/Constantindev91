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


def _parse_ids(raw: str | None) -> list[int]:
    if not raw:
        return []
    out = []
    for part in raw.split(","):
        part = part.strip()
        if part:
            try:
                out.append(int(part))
            except ValueError:
                pass
    return out


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
        give_cards="Tes cartes offertes, IDs séparés par des virgules (ex: 12,15)",
        give_currency=f"Les {config.CURRENCY_SYMBOL} que tu offres en plus",
        want_cards="Les cartes que tu demandes en retour, IDs séparés par des virgules",
        want_currency=f"Les {config.CURRENCY_SYMBOL} que tu demandes en retour",
    )
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

        give_ids = _parse_ids(give_cards)
        want_ids = _parse_ids(want_cards)
        if not give_ids and not give_currency:
            await interaction.response.send_message("❌ Tu dois offrir au moins une carte ou des KP.", ephemeral=True)
            return

        async with SessionLocal() as session:
            await get_or_create_user(session, interaction.user.id)
            await get_or_create_user(session, member.id)

            for cid in give_ids:
                card = await session.get(UserCard, cid)
                if card is None or card.owner_id != interaction.user.id:
                    await interaction.response.send_message(f"❌ La carte `#{cid}` ne t'appartient pas.", ephemeral=True)
                    return
                if card.locked:
                    await interaction.response.send_message(f"❌ La carte `#{cid}` est verrouillée.", ephemeral=True)
                    return
            for cid in want_ids:
                card = await session.get(UserCard, cid)
                if card is None or card.owner_id != member.id:
                    await interaction.response.send_message(f"❌ La carte `#{cid}` n'appartient pas à {member.display_name}.", ephemeral=True)
                    return

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

            give_names, want_names = [], []
            for cid in give_ids:
                card = await session.get(UserCard, cid, options=[selectinload(UserCard.player)])
                give_names.append(card.player.name)
            for cid in want_ids:
                card = await session.get(UserCard, cid, options=[selectinload(UserCard.player)])
                want_names.append(card.player.name)

        embed = discord.Embed(
            title="🔄 Proposition d'échange",
            description=f"{interaction.user.mention} propose un échange à {member.mention} !",
            color=config.rarity_embed_color(4),
        )
        offer_lines = give_names + ([f"{give_currency} {config.CURRENCY_SYMBOL}"] if give_currency else [])
        request_lines = want_names + ([f"{want_currency} {config.CURRENCY_SYMBOL}"] if want_currency else [])
        embed.add_field(name=f"📤 {interaction.user.display_name} offre", value="\n".join(offer_lines) or "Rien", inline=True)
        embed.add_field(name=f"📥 {member.display_name} donne", value="\n".join(request_lines) or "Rien", inline=True)
        embed.set_footer(text=f"Échange #{trade_id} — expire dans 10 minutes")

        view = TradeView(trade_id, interaction.user.id, member.id)
        await interaction.response.send_message(content=member.mention, embed=embed, view=view)

    @trade_group.command(name="cancel", description="Annule un échange que tu as proposé et qui est encore en attente.")
    async def cancel(self, interaction: discord.Interaction, trade_id: int):
        async with SessionLocal() as session:
            trade = await session.get(TradeOffer, trade_id)
            if trade is None or trade.from_user_id != interaction.user.id or trade.status != "pending":
                await interaction.response.send_message("❌ Échange introuvable ou déjà réglé.", ephemeral=True)
                return
            trade.status = "cancelled"
            await session.commit()
        await interaction.response.send_message(f"✅ Échange `#{trade_id}` annulé.")


async def setup(bot: commands.Bot):
    await bot.add_cog(TradeCog(bot))
