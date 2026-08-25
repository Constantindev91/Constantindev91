"""Deterministic-ish match simulation for 1v1 team battles.

Not a physics engine — a lightweight rating model (attack vs defense,
tactic/coach bonuses, equipped technique power) feeding a Poisson-style
goal draw, good enough to make claim rarity / team-building choices
actually matter without needing a full match engine.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field


@dataclass
class StarterCard:
    name: str
    position: str  # GK, DF, MF, FW
    kick: int
    pass_: int
    defense: int
    speed: int
    technique: int
    equipped_technique_power: int | None = None


@dataclass
class TeamPower:
    attack: float
    defense: float
    overall: float
    base_stats: dict[str, float] = field(default_factory=dict)


STAT_KEYS = ("kick", "pass_", "defense", "speed", "technique")


def compute_team_power(
    starters: list[StarterCard],
    tactic_effect: dict[str, int] | None = None,
    coach_bonus: dict[str, int] | None = None,
) -> TeamPower:
    if not starters:
        return TeamPower(attack=1, defense=1, overall=1, base_stats={k: 1 for k in STAT_KEYS})

    base_stats = {k: sum(getattr(c, k) for c in starters) / len(starters) for k in STAT_KEYS}

    equipped_powers = [c.equipped_technique_power for c in starters if c.equipped_technique_power]
    if equipped_powers:
        tech_bonus = (sum(equipped_powers) / len(equipped_powers)) * 0.15
        base_stats["kick"] += tech_bonus
        base_stats["technique"] += tech_bonus * 0.6

    for delta_source in (tactic_effect, coach_bonus):
        if not delta_source:
            continue
        for key, delta in delta_source.items():
            if key in base_stats:
                base_stats[key] += delta

    base_stats = {k: max(1.0, v) for k, v in base_stats.items()}

    attack = base_stats["kick"] * 0.45 + base_stats["technique"] * 0.35 + base_stats["pass_"] * 0.20
    defense = base_stats["defense"] * 0.55 + base_stats["speed"] * 0.25 + base_stats["pass_"] * 0.20
    overall = sum(base_stats.values()) / len(base_stats)

    return TeamPower(attack=attack, defense=defense, overall=overall, base_stats=base_stats)


def _poisson_sample(lam: float, rng: random.Random) -> int:
    """Knuth's algorithm — avoids a numpy dependency for one sampler."""
    lam = max(lam, 0.05)
    l = math.exp(-lam)
    k = 0
    p = 1.0
    while True:
        k += 1
        p *= rng.random()
        if p <= l:
            return k - 1


@dataclass
class MatchResult:
    score_a: int
    score_b: int
    power_a: TeamPower
    power_b: TeamPower

    @property
    def winner(self) -> str:
        if self.score_a > self.score_b:
            return "a"
        if self.score_b > self.score_a:
            return "b"
        return "draw"


def simulate_match(power_a: TeamPower, power_b: TeamPower, seed: int | None = None) -> MatchResult:
    rng = random.Random(seed)
    expected_a = max(0.2, 1.5 + (power_a.attack - power_b.defense) / 16)
    expected_b = max(0.2, 1.5 + (power_b.attack - power_a.defense) / 16)
    score_a = _poisson_sample(expected_a, rng)
    score_b = _poisson_sample(expected_b, rng)
    return MatchResult(score_a=score_a, score_b=score_b, power_a=power_a, power_b=power_b)
