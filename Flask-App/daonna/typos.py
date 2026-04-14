"""Typo generation and realistic correction strategies."""

import random
from dataclasses import dataclass
from typing import Optional, Tuple

from .lexicon import MIRROR_KEYS, get_adjacent_key


# Typo types
ADJACENT = "adjacent"
TRANSPOSITION = "transposition"
DOUBLE = "double"
SKIP = "skip"
MIRROR = "mirror"


# Correction styles
IMMEDIATE = "immediate"      # Notice on next keystroke, burst-correct
DELAYED = "delayed"          # Type 2-5 more chars, freeze, burst-correct
STARE = "stare"              # Notice instantly but pause (the "realization")
IGNORE = "ignore"            # Leave the typo in


@dataclass
class Typo:
    kind: str
    data: object  # char for adjacent/mirror/double, tuple for transposition, None for skip


@dataclass
class CorrectionPlan:
    style: str
    notice_after: int  # extra source chars consumed before correction begins


def maybe_typo(text: str, pos: int, probability: float) -> Optional[Typo]:
    ch = text[pos]
    if not ch.isalnum() or random.random() >= probability:
        return None

    roll = random.random()
    if roll < 0.40:
        return Typo(ADJACENT, get_adjacent_key(ch))
    if roll < 0.65:
        nxt = text[pos + 1] if pos + 1 < len(text) else ""
        if nxt.isalnum():
            return Typo(TRANSPOSITION, (nxt, ch))
        return Typo(ADJACENT, get_adjacent_key(ch))
    if roll < 0.80:
        return Typo(DOUBLE, ch)
    if roll < 0.92:
        return Typo(SKIP, None)
    mirror = MIRROR_KEYS.get(ch.lower())
    if mirror:
        return Typo(MIRROR, mirror.upper() if ch.isupper() else mirror)
    return Typo(ADJACENT, get_adjacent_key(ch))


def plan_correction() -> CorrectionPlan:
    """Pick a correction style with weighted randomness."""
    roll = random.random()
    if roll < 0.55:
        return CorrectionPlan(IMMEDIATE, notice_after=0)
    if roll < 0.75:
        return CorrectionPlan(STARE, notice_after=0)
    if roll < 0.93:
        return CorrectionPlan(DELAYED, notice_after=random.randint(2, 5))
    return CorrectionPlan(IGNORE, notice_after=-1)
