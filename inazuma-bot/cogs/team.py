from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import select
from sqlalchemy.orm import selectinload

import config
from db.database import SessionLocal
from db.models import Team, TeamSlot, UserCard, UserCoach, UserTactic, UserTechnique
from db.repository import get_active_team, get_or_create_user
from utils.autocomplete import owned_card_autocomplete, owned_coach_autocomplete, owned_tactic_autocomplete, owned_technique_autocomplete
from utils.battle_engine import StarterCard, compute_team_power

POSITION_EMOJI = {"GK": "🧤", "DF": "🛡️", "MF": "🎯", "FW": "⚡"}

FORMATION_CHOICES = [app_commands.Choice(name=f, value=f) for f in config.FORMATIONS]


async def _slot_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    async with SessionLocal() as session:
        team = await get_active_team(session, interaction.user.id)
        if team is None:
            return []
        keys = [s.slot_key for s in team.slots]
    filtered = [k for k in keys if current.lower() in k.lower()]
    return [app_commands.Choice(name=k, value=k) for k in filtered[:25]]


class TeamCog(commands.Cog):
    """Composition d'équipe : formation, titulaires, banc, tactique, coach, techniques."""

    team_group = app_commands.Group(name="team", description="Gère la composition de ton équipe")

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _build_lineup_embed(self, session, team: Team, owner: discord.abc.User) -> discord.Embed:
        starters = [s for s in team.slots if not s.is_bench]
        bench = [s for s in team.slots if s.is_bench]

        order = {"GK": 0, "DF": 1, "MF": 2, "FW": 3}
        starters.sort(key=lambda s: order.get(s.slot_key.rstrip("0123456789"), 9))

        lines = []
        starter_cards: list[StarterCard] = []
        for slot in starters:
            label = next((lbl for pos, key, lbl in config.FORMATIONS[team.formation] if key == slot.slot_key), slot.slot_key)
            if slot.card:
                p = slot.card.player
                lines.append(f"`{slot.slot_key}` {label} — {POSITION_EMOJI.get(p.position,'')} **{p.name}** (OVR {p.overall}) `#{slot.card.id}`")
                starter_cards.append(StarterCard(
                    name=p.name, position=p.position, kick=p.kick, pass_=p.pass_,
                    defense=p.defense, speed=p.speed, technique=p.technique,
                ))
            else:
                lines.append(f"`{slot.slot_key}` {label} — _vide_")

        bench_lines = []
        for slot in bench:
            if slot.card:
                p = slot.card.player
                bench_lines.append(f"`{slot.slot_key}` {POSITION_EMOJI.get(p.position,'')} **{p.name}** (OVR {p.overall}) `#{slot.card.id}`")
            else:
                bench_lines.append(f"`{slot.slot_key}` — _vide_")

        power = compute_team_power(
            starter_cards,
            tactic_effect=team.tactic.tactic.effect if team.tactic else None,
            coach_bonus=team.coach.coach.bonus if team.coach else None,
        )

        embed = discord.Embed(
            title=f"👕 {team.name} — {team.formation}",
            color=config.rarity_embed_color(4),
        )
        embed.set_author(name=owner.display_name, icon_url=owner.display_avatar.url)
        embed.add_field(name="🏟️ Titulaires", value="\n".join(lines) or "—", inline=False)
        embed.add_field(name="🪑 Banc", value="\n".join(bench_lines) or "—", inline=False)
        embed.add_field(name="🧠 Tactique", value=team.tactic.tactic.name if team.tactic else "Aucune", inline=True)
        embed.add_field(name="🧑‍💼 Coach", value=team.coach.coach.name if team.coach else "Aucun", inline=True)
        if starter_cards:
            embed.add_field(
                name="📊 Puissance d'équipe",
                value=f"Attaque **{power.attack:.0f}** · Défense **{power.defense:.0f}** · Global **{power.overall:.0f}**",
                inline=False,
            )
        else:
            embed.add_field(name="📊 Puissance d'équipe", value="Place des titulaires pour voir la puissance.", inline=False)
        return embed

    @team_group.command(name="view", description="Affiche la composition actuelle de ton équipe.")
    async def view(self, interaction: discord.Interaction, member: discord.Member | None = None):
        target = member or interaction.user
        async with SessionLocal() as session:
            await get_or_create_user(session, target.id)
            team = await get_active_team(session, target.id)
            if team is None:
                await interaction.response.send_message("Aucune équipe trouvée.", ephemeral=True)
                return
            embed = await self._build_lineup_embed(session, team, target)
        await interaction.response.send_message(embed=embed)

    @team_group.command(name="rename", description="Renomme ton équipe.")
    async def rename(self, interaction: discord.Interaction, name: app_commands.Range[str, 1, 40]):
        async with SessionLocal() as session:
            team = await get_active_team(session, interaction.user.id)
            team.name = name
            await session.commit()
        await interaction.response.send_message(f"✅ Ton équipe s'appelle maintenant **{name}**.")

    @team_group.command(name="formation", description="Change la formation de ton équipe (les titulaires sont réinitialisés).")
    @app_commands.choices(formation=FORMATION_CHOICES)
    async def formation(self, interaction: discord.Interaction, formation: app_commands.Choice[str]):
        async with SessionLocal() as session:
            team = await get_active_team(session, interaction.user.id)
            for slot in list(team.slots):
                if not slot.is_bench:
                    await session.delete(slot)
            await session.flush()
            new_slots = [
                TeamSlot(team_id=team.id, slot_key=key, is_bench=False)
                for _, key, _ in config.FORMATIONS[formation.value]
            ]
            session.add_all(new_slots)
            team.formation = formation.value
            await session.commit()
        await interaction.response.send_message(
            f"✅ Formation changée en **{formation.value}**. Replace tes titulaires avec `/team set`."
        )

    @team_group.command(name="set", description="Place une carte de ta collection dans un slot de ton équipe.")
    @app_commands.describe(slot="Le slot (ex: FW1, DF2, BENCH1 — voir /team view)", card_id="Tape le nom du joueur à placer")
    @app_commands.autocomplete(slot=_slot_autocomplete, card_id=owned_card_autocomplete)
    async def set_slot(self, interaction: discord.Interaction, slot: str, card_id: int):
        async with SessionLocal() as session:
            team = await get_active_team(session, interaction.user.id)
            target_slot = next((s for s in team.slots if s.slot_key == slot), None)
            if target_slot is None:
                await interaction.response.send_message("❌ Slot inconnu. Regarde `/team view`.", ephemeral=True)
                return

            card = await session.get(UserCard, card_id, options=[selectinload(UserCard.player)])
            if card is None or card.owner_id != interaction.user.id:
                await interaction.response.send_message("❌ Cette carte ne t'appartient pas.", ephemeral=True)
                return

            required_position = None
            for pos, key, _ in config.FORMATIONS[team.formation]:
                if key == slot:
                    required_position = pos
                    break
            if required_position and card.player.position != required_position:
                await interaction.response.send_message(
                    f"❌ Ce slot demande un **{required_position}**, mais {card.player.name} est **{card.player.position}**.",
                    ephemeral=True,
                )
                return

            # Free the card from any slot it currently occupies in this team.
            for s in team.slots:
                if s.card_id == card.id:
                    s.card_id = None

            target_slot.card_id = card.id
            await session.commit()

        await interaction.response.send_message(f"✅ **{card.player.name}** placé en `{slot}`.")

    @team_group.command(name="bench", description="Envoie une carte sur le banc (premier slot de banc libre).")
    @app_commands.describe(card_id="Tape le nom du joueur à envoyer sur le banc")
    @app_commands.autocomplete(card_id=owned_card_autocomplete)
    async def bench(self, interaction: discord.Interaction, card_id: int):
        async with SessionLocal() as session:
            team = await get_active_team(session, interaction.user.id)
            card = await session.get(UserCard, card_id, options=[selectinload(UserCard.player)])
            if card is None or card.owner_id != interaction.user.id:
                await interaction.response.send_message("❌ Cette carte ne t'appartient pas.", ephemeral=True)
                return

            free_bench = next((s for s in team.slots if s.is_bench and s.card_id is None), None)
            if free_bench is None:
                await interaction.response.send_message("❌ Ton banc est plein (7 max).", ephemeral=True)
                return

            for s in team.slots:
                if s.card_id == card.id:
                    s.card_id = None
            free_bench.card_id = card.id
            await session.commit()
        await interaction.response.send_message(f"✅ **{card.player.name}** envoyé sur le banc (`{free_bench.slot_key}`).")

    @team_group.command(name="remove", description="Retire une carte d'un slot (titulaire ou banc).")
    @app_commands.autocomplete(slot=_slot_autocomplete)
    async def remove(self, interaction: discord.Interaction, slot: str):
        async with SessionLocal() as session:
            team = await get_active_team(session, interaction.user.id)
            target_slot = next((s for s in team.slots if s.slot_key == slot), None)
            if target_slot is None or target_slot.card_id is None:
                await interaction.response.send_message("❌ Ce slot est déjà vide.", ephemeral=True)
                return
            target_slot.card_id = None
            await session.commit()
        await interaction.response.send_message(f"✅ Slot `{slot}` vidé.")

    @team_group.command(name="tactic", description="Équipe une tactique possédée à ton équipe.")
    @app_commands.describe(user_tactic_id="Tape le nom de la tactique que tu possèdes")
    @app_commands.autocomplete(user_tactic_id=owned_tactic_autocomplete)
    async def tactic(self, interaction: discord.Interaction, user_tactic_id: int):
        async with SessionLocal() as session:
            ut = await session.get(UserTactic, user_tactic_id)
            if ut is None or ut.owner_id != interaction.user.id:
                await interaction.response.send_message("❌ Tu ne possèdes pas cette tactique.", ephemeral=True)
                return
            team = await get_active_team(session, interaction.user.id)
            team.tactic_user_id = ut.id
            await session.commit()
        await interaction.response.send_message("✅ Tactique équipée.")

    @team_group.command(name="coach", description="Équipe un coach possédé à ton équipe.")
    @app_commands.describe(user_coach_id="Tape le nom du coach que tu possèdes")
    @app_commands.autocomplete(user_coach_id=owned_coach_autocomplete)
    async def coach(self, interaction: discord.Interaction, user_coach_id: int):
        async with SessionLocal() as session:
            uc = await session.get(UserCoach, user_coach_id)
            if uc is None or uc.owner_id != interaction.user.id:
                await interaction.response.send_message("❌ Tu ne possèdes pas ce coach.", ephemeral=True)
                return
            team = await get_active_team(session, interaction.user.id)
            team.coach_user_id = uc.id
            await session.commit()
        await interaction.response.send_message("✅ Coach équipé.")

    @team_group.command(name="equip", description="Équipe une technique possédée sur une carte de ton équipe.")
    @app_commands.describe(card_id="Tape le nom du joueur", user_technique_id="Tape le nom de la technique que tu possèdes")
    @app_commands.autocomplete(card_id=owned_card_autocomplete, user_technique_id=owned_technique_autocomplete)
    async def equip(self, interaction: discord.Interaction, card_id: int, user_technique_id: int):
        async with SessionLocal() as session:
            card = await session.get(UserCard, card_id, options=[selectinload(UserCard.player)])
            if card is None or card.owner_id != interaction.user.id:
                await interaction.response.send_message("❌ Cette carte ne t'appartient pas.", ephemeral=True)
                return
            ut = await session.get(UserTechnique, user_technique_id)
            if ut is None or ut.owner_id != interaction.user.id:
                await interaction.response.send_message("❌ Tu ne possèdes pas cette technique.", ephemeral=True)
                return
            card.equipped_technique_id = ut.id
            await session.commit()
        await interaction.response.send_message(f"✅ Technique équipée sur **{card.player.name}**.")

    @team_group.command(name="unequip", description="Retire la technique équipée d'une carte.")
    @app_commands.describe(card_id="Tape le nom du joueur")
    @app_commands.autocomplete(card_id=owned_card_autocomplete)
    async def unequip(self, interaction: discord.Interaction, card_id: int):
        async with SessionLocal() as session:
            card = await session.get(UserCard, card_id, options=[selectinload(UserCard.player)])
            if card is None or card.owner_id != interaction.user.id:
                await interaction.response.send_message("❌ Cette carte ne t'appartient pas.", ephemeral=True)
                return
            card.equipped_technique_id = None
            await session.commit()
        await interaction.response.send_message(f"✅ Technique retirée de **{card.player.name}**.")


async def setup(bot: commands.Bot):
    await bot.add_cog(TeamCog(bot))
