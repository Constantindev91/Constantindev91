"""SQLAlchemy ORM models for INAZUMA BOT."""
from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Master data (seeded from data/*.json, read-mostly)
# ---------------------------------------------------------------------------

class PlayerTemplate(Base):
    __tablename__ = "player_templates"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    name_en: Mapped[str] = mapped_column(String)
    team_origin: Mapped[str] = mapped_column(String)
    series: Mapped[str] = mapped_column(String)
    position: Mapped[str] = mapped_column(String)  # GK, DF, MF, FW
    element: Mapped[str] = mapped_column(String)
    rarity: Mapped[int] = mapped_column(Integer)
    kick: Mapped[int] = mapped_column(Integer)
    pass_: Mapped[int] = mapped_column("pass", Integer)
    defense: Mapped[int] = mapped_column(Integer)
    speed: Mapped[int] = mapped_column(Integer)
    technique: Mapped[int] = mapped_column(Integer)
    signature_technique: Mapped[str | None] = mapped_column(String, nullable=True)
    flavor: Mapped[str] = mapped_column(String)
    base_price: Mapped[int] = mapped_column(Integer, default=0)
    # Optional override: a real picture URL supplied by the server admin. When set, the
    # bot shows this image instead of the generated portrait card. Never auto-filled by
    # the bot itself — see data/players.json / README for how to set it.
    image_url: Mapped[str | None] = mapped_column(String, nullable=True)

    @property
    def overall(self) -> int:
        return round((self.kick + self.pass_ + self.defense + self.speed + self.technique) / 5)


class TechniqueTemplate(Base):
    __tablename__ = "technique_templates"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    type: Mapped[str] = mapped_column(String)  # shoot, dribble, block, catch
    element: Mapped[str] = mapped_column(String)
    power: Mapped[int] = mapped_column(Integer)
    rarity: Mapped[int] = mapped_column(Integer)
    description: Mapped[str] = mapped_column(String)
    image_url: Mapped[str | None] = mapped_column(String, nullable=True)


class TacticTemplate(Base):
    __tablename__ = "tactic_templates"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    effect: Mapped[dict] = mapped_column(JSON)
    rarity: Mapped[int] = mapped_column(Integer)
    description: Mapped[str] = mapped_column(String)


class CoachTemplate(Base):
    __tablename__ = "coach_templates"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    team_origin: Mapped[str] = mapped_column(String)
    bonus: Mapped[dict] = mapped_column(JSON)
    rarity: Mapped[int] = mapped_column(Integer)
    description: Mapped[str] = mapped_column(String)
    image_url: Mapped[str | None] = mapped_column(String, nullable=True)


# ---------------------------------------------------------------------------
# User-owned data
# ---------------------------------------------------------------------------

class User(Base):
    __tablename__ = "users"

    discord_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    currency: Mapped[int] = mapped_column(Integer, default=0)
    rank_points: Mapped[int] = mapped_column(Integer, default=0)
    wins: Mapped[int] = mapped_column(Integer, default=0)
    losses: Mapped[int] = mapped_column(Integer, default=0)
    draws: Mapped[int] = mapped_column(Integer, default=0)
    last_claim: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    last_daily: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    active_team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)

    cards: Mapped[list["UserCard"]] = relationship(
        back_populates="owner", foreign_keys="UserCard.owner_id"
    )
    teams: Mapped[list["Team"]] = relationship(
        back_populates="owner", foreign_keys="Team.owner_id"
    )


class UserCard(Base):
    __tablename__ = "user_cards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.discord_id"))
    player_id: Mapped[str] = mapped_column(ForeignKey("player_templates.id"))
    obtained_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)
    equipped_technique_id: Mapped[int | None] = mapped_column(
        ForeignKey("user_techniques.id"), nullable=True
    )
    locked: Mapped[bool] = mapped_column(Boolean, default=False)

    owner: Mapped["User"] = relationship(back_populates="cards", foreign_keys=[owner_id])
    player: Mapped["PlayerTemplate"] = relationship()
    equipped_technique: Mapped["UserTechnique | None"] = relationship(
        foreign_keys=[equipped_technique_id]
    )


class UserTechnique(Base):
    __tablename__ = "user_techniques"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.discord_id"))
    technique_id: Mapped[str] = mapped_column(ForeignKey("technique_templates.id"))
    acquired_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)

    technique: Mapped["TechniqueTemplate"] = relationship()


class UserTactic(Base):
    __tablename__ = "user_tactics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.discord_id"))
    tactic_id: Mapped[str] = mapped_column(ForeignKey("tactic_templates.id"))

    tactic: Mapped["TacticTemplate"] = relationship()


class UserCoach(Base):
    __tablename__ = "user_coaches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.discord_id"))
    coach_id: Mapped[str] = mapped_column(ForeignKey("coach_templates.id"))

    coach: Mapped["CoachTemplate"] = relationship()


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.discord_id"))
    name: Mapped[str] = mapped_column(String, default="Mon Équipe")
    formation: Mapped[str] = mapped_column(String, default="4-4-2")
    tactic_user_id: Mapped[int | None] = mapped_column(ForeignKey("user_tactics.id"), nullable=True)
    coach_user_id: Mapped[int | None] = mapped_column(ForeignKey("user_coaches.id"), nullable=True)

    owner: Mapped["User"] = relationship(back_populates="teams", foreign_keys=[owner_id])
    slots: Mapped[list["TeamSlot"]] = relationship(back_populates="team", cascade="all, delete-orphan")
    tactic: Mapped["UserTactic | None"] = relationship(foreign_keys=[tactic_user_id])
    coach: Mapped["UserCoach | None"] = relationship(foreign_keys=[coach_user_id])


class TeamSlot(Base):
    __tablename__ = "team_slots"
    __table_args__ = (UniqueConstraint("team_id", "slot_key", name="uq_team_slot"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    slot_key: Mapped[str] = mapped_column(String)  # GK, DF1.., MF1.., FW1.., BENCH1..BENCH7
    is_bench: Mapped[bool] = mapped_column(Boolean, default=False)
    card_id: Mapped[int | None] = mapped_column(ForeignKey("user_cards.id"), nullable=True)

    team: Mapped["Team"] = relationship(back_populates="slots")
    card: Mapped["UserCard | None"] = relationship()


class MarketListing(Base):
    __tablename__ = "market_listings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    seller_id: Mapped[int] = mapped_column(ForeignKey("users.discord_id"))
    card_id: Mapped[int] = mapped_column(ForeignKey("user_cards.id"))
    price: Mapped[int] = mapped_column(Integer)
    listed_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    card: Mapped["UserCard"] = relationship()


class TradeOffer(Base):
    __tablename__ = "trade_offers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    from_user_id: Mapped[int] = mapped_column(ForeignKey("users.discord_id"))
    to_user_id: Mapped[int] = mapped_column(ForeignKey("users.discord_id"))
    offer_card_ids: Mapped[list] = mapped_column(JSON, default=list)
    offer_currency: Mapped[int] = mapped_column(Integer, default=0)
    request_card_ids: Mapped[list] = mapped_column(JSON, default=list)
    request_currency: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String, default="pending")  # pending/accepted/declined/cancelled
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)


class BattleLog(Base):
    __tablename__ = "battle_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_a: Mapped[int] = mapped_column(ForeignKey("users.discord_id"))
    user_b: Mapped[int] = mapped_column(ForeignKey("users.discord_id"))
    score_a: Mapped[int] = mapped_column(Integer)
    score_b: Mapped[int] = mapped_column(Integer)
    winner_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    rank_change_a: Mapped[int] = mapped_column(Integer)
    rank_change_b: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)
