"""Async SQLAlchemy engine/session management + one-shot data seeding."""
from __future__ import annotations

import json

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import config
from db.models import (
    Base,
    CoachTemplate,
    PlayerTemplate,
    TacticTemplate,
    TechniqueTemplate,
)

engine = create_async_engine(config.DATABASE_URL, echo=False)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def init_db() -> None:
    """Create tables (if needed) and load master data from data/*.json.

    Master data rows are upserted by primary key so re-running this on
    startup keeps existing tables and simply refreshes the reference data
    (useful when data/*.json is edited/extended between runs).
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with SessionLocal() as session:
        await _seed_players(session)
        await _seed_techniques(session)
        await _seed_tactics(session)
        await _seed_coaches(session)
        await session.commit()


def _load_json(name: str) -> list[dict]:
    path = config.DATA_DIR / name
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


async def _seed_players(session: AsyncSession) -> None:
    rows = _load_json("players.json")
    for row in rows:
        obj = await session.get(PlayerTemplate, row["id"])
        stats = row["stats"]
        if obj is None:
            obj = PlayerTemplate(id=row["id"])
            session.add(obj)
        obj.name = row["name"]
        obj.name_en = row["name_en"]
        obj.team_origin = row["team_origin"]
        obj.series = row["series"]
        obj.position = row["position"]
        obj.element = row["element"]
        obj.rarity = row["rarity"]
        obj.kick = stats["kick"]
        obj.pass_ = stats["pass"]
        obj.defense = stats["defense"]
        obj.speed = stats["speed"]
        obj.technique = stats["technique"]
        obj.signature_technique = row.get("signature_technique")
        obj.flavor = row["flavor"]
        obj.base_price = row.get("base_price", 0)
        obj.image_url = row.get("image_url") or None


async def _seed_techniques(session: AsyncSession) -> None:
    rows = _load_json("techniques.json")
    for row in rows:
        obj = await session.get(TechniqueTemplate, row["id"])
        if obj is None:
            obj = TechniqueTemplate(id=row["id"])
            session.add(obj)
        obj.name = row["name"]
        obj.type = row["type"]
        obj.element = row["element"]
        obj.power = row["power"]
        obj.rarity = row["rarity"]
        obj.description = row["description"]
        obj.image_url = row.get("image_url") or None


async def _seed_tactics(session: AsyncSession) -> None:
    rows = _load_json("tactics.json")
    for row in rows:
        obj = await session.get(TacticTemplate, row["id"])
        if obj is None:
            obj = TacticTemplate(id=row["id"])
            session.add(obj)
        obj.name = row["name"]
        obj.effect = row["effect"]
        obj.rarity = row["rarity"]
        obj.description = row["description"]


async def _seed_coaches(session: AsyncSession) -> None:
    rows = _load_json("coaches.json")
    for row in rows:
        obj = await session.get(CoachTemplate, row["id"])
        if obj is None:
            obj = CoachTemplate(id=row["id"])
            session.add(obj)
        obj.name = row["name"]
        obj.team_origin = row["team_origin"]
        obj.bonus = row["bonus"]
        obj.rarity = row["rarity"]
        obj.description = row["description"]
        obj.image_url = row.get("image_url") or None
