"""Shared data-access helpers used across cogs.

Keeping these in one place avoids every cog re-implementing
get-or-create-user, team lookups, etc.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

import config
from db.models import Team, TeamSlot, User


async def get_or_create_user(session: AsyncSession, discord_id: int) -> User:
    user = await session.get(User, discord_id)
    if user is None:
        user = User(discord_id=discord_id, currency=config.STARTING_CURRENCY)
        session.add(user)
        await session.flush()
        team = Team(owner_id=discord_id, name="Mon Équipe", formation="4-4-2")
        session.add(team)
        await session.flush()
        session.add_all(_build_slots_for_formation(team.id, "4-4-2"))
        user.active_team_id = team.id
        await session.flush()
    return user


def _build_slots_for_formation(team_id: int, formation: str) -> list[TeamSlot]:
    """Build a fresh (unattached) list of slots for a team — caller adds them to the session."""
    slots: list[TeamSlot] = []
    for _, slot_key, _ in config.FORMATIONS[formation]:
        slots.append(TeamSlot(team_id=team_id, slot_key=slot_key, is_bench=False))
    for i in range(1, config.BENCH_SIZE + 1):
        slots.append(TeamSlot(team_id=team_id, slot_key=f"BENCH{i}", is_bench=True))
    return slots


async def get_active_team(session: AsyncSession, discord_id: int) -> Team | None:
    user = await session.get(User, discord_id)
    if user is None or user.active_team_id is None:
        return None
    result = await session.execute(
        select(Team)
        .where(Team.id == user.active_team_id)
        .options(
            selectinload(Team.slots).selectinload(TeamSlot.card),
            selectinload(Team.tactic),
            selectinload(Team.coach),
        )
    )
    return result.scalar_one_or_none()


def claim_on_cooldown(user: User) -> dt.timedelta | None:
    if user.last_claim is None:
        return None
    elapsed = dt.datetime.utcnow() - user.last_claim
    remaining = dt.timedelta(seconds=config.CLAIM_COOLDOWN_SECONDS) - elapsed
    return remaining if remaining.total_seconds() > 0 else None


def daily_on_cooldown(user: User) -> dt.timedelta | None:
    if user.last_daily is None:
        return None
    elapsed = dt.datetime.utcnow() - user.last_daily
    remaining = dt.timedelta(seconds=config.DAILY_COOLDOWN_SECONDS) - elapsed
    return remaining if remaining.total_seconds() > 0 else None


def format_timedelta(td: dt.timedelta) -> str:
    total_seconds = int(td.total_seconds())
    minutes, seconds = divmod(total_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minutes}min {seconds}s"
    if minutes:
        return f"{minutes}min {seconds}s"
    return f"{seconds}s"
