from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import select

import config
from db.database import SessionLocal
from db.models import CoachTemplate, TacticTemplate, TechniqueTemplate, User, UserCoach, UserTactic, UserTechnique
from db.repository import get_or_create_user
from utils.autocomplete import coach_autocomplete, tactic_autocomplete, technique_autocomplete
from utils.icon_render import CoachData, TechniqueData, render_coach_card, render_technique_card
from utils.pagination import Paginator, chunk

TYPE_EMOJI = {"shoot": "🥅", "dribble": "🏃", "block": "🛑", "catch": "🧤"}


class ShopCog(commands.Cog):
    """Boutique : techniques, tactiques et coachs, plus ton inventaire."""

    shop_group = app_commands.Group(name="shop", description="Parcourt et achète dans la boutique INAZUMA BOT")
    buy_group = app_commands.Group(name="buy", description="Achète un objet de la boutique", parent=shop_group)

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @shop_group.command(name="techniques", description="Liste les techniques (hissatsu) disponibles à l'achat.")
    async def shop_techniques(self, interaction: discord.Interaction):
        async with SessionLocal() as session:
            rows = list((await session.execute(select(TechniqueTemplate).order_by(TechniqueTemplate.rarity.desc(), TechniqueTemplate.name))).scalars().all())

        pages = []
        for group in chunk(rows, 10):
            lines = [
                f"{TYPE_EMOJI.get(t.type,'')} {config.RARITY_STARS[t.rarity]} **{t.name}** "
                f"({t.type}, {t.element}, PUI {t.power}) — {config.shop_price(t.rarity)} {config.CURRENCY_SYMBOL}"
                for t in group
            ]
            embed = discord.Embed(title="🎴 Boutique — Techniques", description="\n".join(lines), color=config.rarity_embed_color(4))
            embed.set_footer(text="Achète avec /shop buy technique (tape le nom)")
            pages.append(embed)
        await interaction.response.send_message(embed=pages[0], view=Paginator(interaction.user.id, pages))

    @shop_group.command(name="tactics", description="Liste les tactiques d'équipe disponibles à l'achat.")
    async def shop_tactics(self, interaction: discord.Interaction):
        async with SessionLocal() as session:
            rows = list((await session.execute(select(TacticTemplate).order_by(TacticTemplate.rarity.desc(), TacticTemplate.name))).scalars().all())

        pages = []
        for group in chunk(rows, 10):
            lines = [
                f"{config.RARITY_STARS[t.rarity]} **{t.name}** — {t.effect} — {config.shop_price(t.rarity)} {config.CURRENCY_SYMBOL}"
                for t in group
            ]
            embed = discord.Embed(title="🧠 Boutique — Tactiques", description="\n".join(lines), color=config.rarity_embed_color(4))
            embed.set_footer(text="Achète avec /shop buy tactic (tape le nom)")
            pages.append(embed)
        await interaction.response.send_message(embed=pages[0], view=Paginator(interaction.user.id, pages))

    @shop_group.command(name="coaches", description="Liste les coachs disponibles à l'achat.")
    async def shop_coaches(self, interaction: discord.Interaction):
        async with SessionLocal() as session:
            rows = list((await session.execute(select(CoachTemplate).order_by(CoachTemplate.rarity.desc(), CoachTemplate.name))).scalars().all())

        pages = []
        for group in chunk(rows, 10):
            lines = [
                f"{config.RARITY_STARS[c.rarity]} **{c.name}** ({c.team_origin}) — {c.bonus} — {config.shop_price(c.rarity)} {config.CURRENCY_SYMBOL}"
                for c in group
            ]
            embed = discord.Embed(title="🧑‍💼 Boutique — Coachs", description="\n".join(lines), color=config.rarity_embed_color(4))
            embed.set_footer(text="Achète avec /shop buy coach (tape le nom)")
            pages.append(embed)
        await interaction.response.send_message(embed=pages[0], view=Paginator(interaction.user.id, pages))

    @app_commands.command(name="technique", description="Affiche la carte détaillée (avec image) d'une technique.")
    @app_commands.describe(technique="Tape le nom de la technique")
    @app_commands.autocomplete(technique=technique_autocomplete)
    async def technique_view(self, interaction: discord.Interaction, technique: str):
        async with SessionLocal() as session:
            t = await session.get(TechniqueTemplate, technique)
        if t is None:
            await interaction.response.send_message("❌ Technique introuvable — tape un bout de son nom et choisis une suggestion.", ephemeral=True)
            return

        embed = discord.Embed(
            title=f"{TYPE_EMOJI.get(t.type,'')} {t.name}",
            description=f"{config.RARITY_STARS[t.rarity]} ({t.rarity}/5) — prix boutique : {config.shop_price(t.rarity)} {config.CURRENCY_SYMBOL}\n_{t.description}_",
            color=config.rarity_embed_color(t.rarity),
        )
        if t.image_url:
            embed.set_image(url=t.image_url)
            await interaction.response.send_message(embed=embed)
        else:
            buf = render_technique_card(TechniqueData(id=t.id, name=t.name, type=t.type, element=t.element, power=t.power, rarity=t.rarity, description=t.description))
            file = discord.File(buf, filename="technique.png")
            embed.set_image(url="attachment://technique.png")
            await interaction.response.send_message(embed=embed, file=file)

    @app_commands.command(name="coach", description="Affiche la carte détaillée (avec image) d'un coach.")
    @app_commands.describe(coach="Tape le nom du coach")
    @app_commands.autocomplete(coach=coach_autocomplete)
    async def coach_view(self, interaction: discord.Interaction, coach: str):
        async with SessionLocal() as session:
            c = await session.get(CoachTemplate, coach)
        if c is None:
            await interaction.response.send_message("❌ Coach introuvable — tape un bout de son nom et choisis une suggestion.", ephemeral=True)
            return

        embed = discord.Embed(
            title=f"🧑‍💼 {c.name}",
            description=f"{config.RARITY_STARS[c.rarity]} ({c.rarity}/5) — prix boutique : {config.shop_price(c.rarity)} {config.CURRENCY_SYMBOL}\n_{c.description}_",
            color=config.rarity_embed_color(c.rarity),
        )
        if c.image_url:
            embed.set_image(url=c.image_url)
            await interaction.response.send_message(embed=embed)
        else:
            buf = render_coach_card(CoachData(id=c.id, name=c.name, team_origin=c.team_origin, bonus=c.bonus, rarity=c.rarity, description=c.description))
            file = discord.File(buf, filename="coach.png")
            embed.set_image(url="attachment://coach.png")
            await interaction.response.send_message(embed=embed, file=file)

    async def _charge(self, session, user_id: int, price: int) -> User | None:
        user = await session.get(User, user_id)
        if user is None or user.currency < price:
            return None
        user.currency -= price
        return user

    @buy_group.command(name="technique", description="Achète une technique de la boutique.")
    @app_commands.describe(technique="Tape le nom de la technique")
    @app_commands.autocomplete(technique=technique_autocomplete)
    async def buy_technique(self, interaction: discord.Interaction, technique: str):
        async with SessionLocal() as session:
            await get_or_create_user(session, interaction.user.id)
            template = await session.get(TechniqueTemplate, technique)
            if template is None:
                await interaction.response.send_message("❌ Technique introuvable.", ephemeral=True)
                return
            price = config.shop_price(template.rarity)
            user = await self._charge(session, interaction.user.id, price)
            if user is None:
                await interaction.response.send_message(f"❌ Il te faut **{price} {config.CURRENCY_SYMBOL}**.", ephemeral=True)
                return
            session.add(UserTechnique(owner_id=interaction.user.id, technique_id=template.id))
            await session.commit()
        await interaction.response.send_message(f"✅ Tu as acheté **{template.name}** pour {price} {config.CURRENCY_SYMBOL} !")

    @buy_group.command(name="tactic", description="Achète une tactique de la boutique.")
    @app_commands.describe(tactique="Tape le nom de la tactique")
    @app_commands.autocomplete(tactique=tactic_autocomplete)
    async def buy_tactic(self, interaction: discord.Interaction, tactique: str):
        async with SessionLocal() as session:
            await get_or_create_user(session, interaction.user.id)
            template = await session.get(TacticTemplate, tactique)
            if template is None:
                await interaction.response.send_message("❌ Tactique introuvable.", ephemeral=True)
                return
            price = config.shop_price(template.rarity)
            user = await self._charge(session, interaction.user.id, price)
            if user is None:
                await interaction.response.send_message(f"❌ Il te faut **{price} {config.CURRENCY_SYMBOL}**.", ephemeral=True)
                return
            session.add(UserTactic(owner_id=interaction.user.id, tactic_id=template.id))
            await session.commit()
        await interaction.response.send_message(f"✅ Tu as acheté **{template.name}** pour {price} {config.CURRENCY_SYMBOL} !")

    @buy_group.command(name="coach", description="Achète un coach de la boutique.")
    @app_commands.describe(coach="Tape le nom du coach")
    @app_commands.autocomplete(coach=coach_autocomplete)
    async def buy_coach(self, interaction: discord.Interaction, coach: str):
        async with SessionLocal() as session:
            await get_or_create_user(session, interaction.user.id)
            template = await session.get(CoachTemplate, coach)
            if template is None:
                await interaction.response.send_message("❌ Coach introuvable.", ephemeral=True)
                return
            price = config.shop_price(template.rarity)
            user = await self._charge(session, interaction.user.id, price)
            if user is None:
                await interaction.response.send_message(f"❌ Il te faut **{price} {config.CURRENCY_SYMBOL}**.", ephemeral=True)
                return
            session.add(UserCoach(owner_id=interaction.user.id, coach_id=template.id))
            await session.commit()
        await interaction.response.send_message(f"✅ Tu as recruté le coach **{template.name}** pour {price} {config.CURRENCY_SYMBOL} !")

    @app_commands.command(name="inventory", description="Liste tes techniques, tactiques et coachs possédés.")
    async def inventory(self, interaction: discord.Interaction):
        async with SessionLocal() as session:
            techs = list((await session.execute(select(UserTechnique).where(UserTechnique.owner_id == interaction.user.id))).scalars().all())
            tactics = list((await session.execute(select(UserTactic).where(UserTactic.owner_id == interaction.user.id))).scalars().all())
            coaches = list((await session.execute(select(UserCoach).where(UserCoach.owner_id == interaction.user.id))).scalars().all())

            tech_lines = []
            for t in techs:
                tpl = await session.get(TechniqueTemplate, t.technique_id)
                tech_lines.append(f"{config.RARITY_STARS[tpl.rarity]} {tpl.name}")
            tactic_lines = []
            for t in tactics:
                tpl = await session.get(TacticTemplate, t.tactic_id)
                tactic_lines.append(f"{config.RARITY_STARS[tpl.rarity]} {tpl.name}")
            coach_lines = []
            for c in coaches:
                tpl = await session.get(CoachTemplate, c.coach_id)
                coach_lines.append(f"{config.RARITY_STARS[tpl.rarity]} {tpl.name}")

        embed = discord.Embed(title=f"🎒 Inventaire de {interaction.user.display_name}", color=config.rarity_embed_color(3))
        embed.add_field(name="🎴 Techniques", value="\n".join(tech_lines) or "Aucune — `/shop techniques`", inline=False)
        embed.add_field(name="🧠 Tactiques", value="\n".join(tactic_lines) or "Aucune — `/shop tactics`", inline=False)
        embed.add_field(name="🧑‍💼 Coachs", value="\n".join(coach_lines) or "Aucun — `/shop coaches`", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(ShopCog(bot))
