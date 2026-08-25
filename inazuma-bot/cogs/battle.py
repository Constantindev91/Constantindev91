from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

import config
from db.database import SessionLocal
from db.models import BattleLog, Team, TechniqueTemplate, User, UserTechnique
from db.repository import get_active_team, get_or_create_user
from utils.battle_engine import StarterCard, compute_team_power, simulate_match


async def _build_starters(session, team: Team) -> list[StarterCard] | None:
    """Returns None if the lineup is incomplete (any of the 11 starting slots is empty)."""
    starters = [s for s in team.slots if not s.is_bench]
    cards = []
    for slot in starters:
        if slot.card is None:
            return None
        p = slot.card.player
        technique_id = None
        if slot.card.equipped_technique_id:
            ut = await session.get(UserTechnique, slot.card.equipped_technique_id)
            if ut:
                technique_id = ut.technique_id
        elif p.signature_technique:
            technique_id = p.signature_technique

        power = None
        if technique_id:
            tt = await session.get(TechniqueTemplate, technique_id)
            power = tt.power if tt else None

        cards.append(StarterCard(
            name=p.name, position=p.position, kick=p.kick, pass_=p.pass_,
            defense=p.defense, speed=p.speed, technique=p.technique,
            equipped_technique_power=power,
        ))
    return cards


class BattleChallengeView(discord.ui.View):
    def __init__(self, challenger_id: int, opponent_id: int, cog: "BattleCog"):
        super().__init__(timeout=120)
        self.challenger_id = challenger_id
        self.opponent_id = opponent_id
        self.cog = cog

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.opponent_id:
            await interaction.response.send_message("Seul le membre défié peut répondre.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Accepter le défi", style=discord.ButtonStyle.success, emoji="⚽")
    async def accept(self, interaction: discord.Interaction, _: discord.ui.Button):
        for item in self.children:
            item.disabled = True  # type: ignore[attr-defined]
        await interaction.response.edit_message(content="⏳ Match en cours de simulation...", view=self)
        await self.cog.run_match(interaction, self.challenger_id, self.opponent_id)
        self.stop()

    @discord.ui.button(label="Refuser", style=discord.ButtonStyle.danger, emoji="🚫")
    async def decline(self, interaction: discord.Interaction, _: discord.ui.Button):
        for item in self.children:
            item.disabled = True  # type: ignore[attr-defined]
        await interaction.response.edit_message(content="🚫 Défi refusé.", view=self)
        self.stop()


class BattleCog(commands.Cog):
    """Combats 1v1 entre équipes de membres du serveur, avec classement ranked."""

    battle_group = app_commands.Group(name="battle", description="Défie un autre membre en 1v1")

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @battle_group.command(name="challenge", description="Défie un autre membre en 1v1 équipe contre équipe.")
    async def challenge(self, interaction: discord.Interaction, member: discord.Member):
        if member.id == interaction.user.id:
            await interaction.response.send_message("❌ Tu ne peux pas te défier toi-même.", ephemeral=True)
            return
        if member.bot:
            await interaction.response.send_message("❌ Impossible de défier un bot.", ephemeral=True)
            return

        async with SessionLocal() as session:
            await get_or_create_user(session, interaction.user.id)
            await get_or_create_user(session, member.id)
            team_a = await get_active_team(session, interaction.user.id)
            team_b = await get_active_team(session, member.id)
            starters_a = await _build_starters(session, team_a) if team_a else None
            starters_b = await _build_starters(session, team_b) if team_b else None

        if starters_a is None:
            await interaction.response.send_message("❌ Ton équipe n'a pas ses 11 titulaires complets (`/team view`).", ephemeral=True)
            return
        if starters_b is None:
            await interaction.response.send_message(f"❌ L'équipe de {member.display_name} n'a pas ses 11 titulaires complets.", ephemeral=True)
            return

        embed = discord.Embed(
            title="⚔️ Défi lancé !",
            description=f"{interaction.user.mention} défie {member.mention} en 1v1 classé !\n{member.mention}, acceptes-tu ?",
            color=config.rarity_embed_color(4),
        )
        view = BattleChallengeView(interaction.user.id, member.id, self)
        await interaction.response.send_message(content=member.mention, embed=embed, view=view)

    async def run_match(self, interaction: discord.Interaction, challenger_id: int, opponent_id: int) -> None:
        async with SessionLocal() as session:
            user_a = await session.get(User, challenger_id)
            user_b = await session.get(User, opponent_id)
            team_a = await get_active_team(session, challenger_id)
            team_b = await get_active_team(session, opponent_id)
            starters_a = await _build_starters(session, team_a)
            starters_b = await _build_starters(session, team_b)

            if starters_a is None or starters_b is None:
                await interaction.followup.send("❌ Une des deux équipes n'est plus complète, match annulé.")
                return

            power_a = compute_team_power(
                starters_a,
                tactic_effect=team_a.tactic.tactic.effect if team_a.tactic else None,
                coach_bonus=team_a.coach.coach.bonus if team_a.coach else None,
            )
            power_b = compute_team_power(
                starters_b,
                tactic_effect=team_b.tactic.tactic.effect if team_b.tactic else None,
                coach_bonus=team_b.coach.coach.bonus if team_b.coach else None,
            )
            result = simulate_match(power_a, power_b)

            if result.winner == "a":
                rank_a, rank_b = config.RANK_POINTS_WIN, config.RANK_POINTS_LOSS
                reward_a, reward_b = config.BATTLE_REWARD_WIN, config.BATTLE_REWARD_LOSS
                user_a.wins += 1
                user_b.losses += 1
                winner_id = challenger_id
            elif result.winner == "b":
                rank_a, rank_b = config.RANK_POINTS_LOSS, config.RANK_POINTS_WIN
                reward_a, reward_b = config.BATTLE_REWARD_LOSS, config.BATTLE_REWARD_WIN
                user_a.losses += 1
                user_b.wins += 1
                winner_id = opponent_id
            else:
                rank_a = rank_b = config.RANK_POINTS_DRAW
                reward_a = reward_b = config.BATTLE_REWARD_DRAW
                user_a.draws += 1
                user_b.draws += 1
                winner_id = None

            user_a.rank_points = max(0, user_a.rank_points + rank_a)
            user_b.rank_points = max(0, user_b.rank_points + rank_b)
            user_a.currency += reward_a
            user_b.currency += reward_b

            session.add(BattleLog(
                user_a=challenger_id, user_b=opponent_id,
                score_a=result.score_a, score_b=result.score_b,
                winner_id=winner_id, rank_change_a=rank_a, rank_change_b=rank_b,
            ))
            await session.commit()

            tier_a = config.rank_tier_for_points(user_a.rank_points)
            tier_b = config.rank_tier_for_points(user_b.rank_points)

        challenger = await interaction.client.fetch_user(challenger_id)
        opponent = await interaction.client.fetch_user(opponent_id)

        if result.winner == "draw":
            title = "🤝 Match nul !"
        else:
            winner_name = challenger.display_name if result.winner == "a" else opponent.display_name
            title = f"🏆 Victoire de {winner_name} !"

        embed = discord.Embed(title=title, color=config.rarity_embed_color(5))
        embed.add_field(
            name=challenger.display_name,
            value=(
                f"Score : **{result.score_a}**\nAttaque {power_a.attack:.0f} / Défense {power_a.defense:.0f}\n"
                f"{'+' if rank_a >= 0 else ''}{rank_a} pts ({tier_a}) · +{reward_a} {config.CURRENCY_SYMBOL}"
            ),
            inline=True,
        )
        embed.add_field(
            name=opponent.display_name,
            value=(
                f"Score : **{result.score_b}**\nAttaque {power_b.attack:.0f} / Défense {power_b.defense:.0f}\n"
                f"{'+' if rank_b >= 0 else ''}{rank_b} pts ({tier_b}) · +{reward_b} {config.CURRENCY_SYMBOL}"
            ),
            inline=True,
        )
        embed.description = f"**{result.score_a} — {result.score_b}**"
        await interaction.followup.send(embed=embed)

    @battle_group.command(name="history", description="Affiche tes 5 derniers combats.")
    async def history(self, interaction: discord.Interaction):
        from sqlalchemy import or_, select

        async with SessionLocal() as session:
            stmt = (
                select(BattleLog)
                .where(or_(BattleLog.user_a == interaction.user.id, BattleLog.user_b == interaction.user.id))
                .order_by(BattleLog.created_at.desc())
                .limit(5)
            )
            logs = list((await session.execute(stmt)).scalars().all())

        if not logs:
            await interaction.response.send_message("Aucun combat pour le moment. Utilise `/battle challenge` !", ephemeral=True)
            return

        lines = []
        for log in logs:
            opponent_id = log.user_b if log.user_a == interaction.user.id else log.user_a
            my_score = log.score_a if log.user_a == interaction.user.id else log.score_b
            opp_score = log.score_b if log.user_a == interaction.user.id else log.score_a
            if log.winner_id is None:
                result = "🤝 Nul"
            elif log.winner_id == interaction.user.id:
                result = "✅ Victoire"
            else:
                result = "❌ Défaite"
            lines.append(f"{result} **{my_score}-{opp_score}** vs <@{opponent_id}>")

        embed = discord.Embed(title=f"📜 Historique de {interaction.user.display_name}", description="\n".join(lines), color=config.rarity_embed_color(3))
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(BattleCog(bot))
