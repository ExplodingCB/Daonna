"""Timing model: AR(1) momentum, chunk bursts, stochastic fatigue, thinking pauses."""

import math
import random
from dataclasses import dataclass

from .lexicon import (
    COMMON_WORDS,
    CONJUNCTIONS,
    current_ngram_multiplier,
    is_word_boundary,
    word_at_position,
)


@dataclass
class RhythmConfig:
    wpm: float
    randomness: float  # 0.0 .. 1.0
    momentum: float = 0.45  # AR(1) coefficient alpha
    # Each run gets its own fatigue seed so the curve looks different every time.
    fatigue_seed: float = 0.0


class RhythmState:
    """Per-run mutable state: previous delay (for AR(1)) and fatigue walk."""

    def __init__(self, cfg: RhythmConfig):
        self.cfg = cfg
        self.base_delay = 60.0 / max(cfg.wpm, 1.0) / 5.0
        self.prev_delay = self.base_delay
        # Random walk value around 1.0, clamped. Seeded for variety per run.
        self._walk = 1.0
        self._rng = random.Random(cfg.fatigue_seed or None)

    # ------------- core distributions -------------

    def _lognormal(self, target: float, sigma_scale: float = 1.0) -> float:
        sigma = max(0.05, 0.35 * self.cfg.randomness * sigma_scale)
        mu = math.log(max(target, 1e-4))
        v = random.lognormvariate(mu, sigma)
        return max(0.008, min(v, target * 8))

    def _fatigue_step(self, progress: float) -> float:
        """Stochastic envelope drifting around 1.0, trending up after 75%."""
        # Slow drift
        self._walk += self._rng.uniform(-0.02, 0.02)
        self._walk = max(0.85, min(self._walk, 1.25))
        # Deterministic trend component
        if progress < 0.05:
            trend = 1.25 - (progress / 0.05) * 0.25  # warmup
        elif progress < 0.75:
            trend = 0.96
        else:
            trend = 1.0 + (progress - 0.75) / 0.25 * 0.18  # fatigue climb
        return 0.5 * self._walk + 0.5 * trend

    # ------------- public API -------------

    def keystroke_delay(self, text: str, pos: int) -> float:
        """Delay AFTER typing text[pos], before moving on."""
        total = len(text)
        progress = pos / max(total, 1)
        fatigue = self._fatigue_step(progress)

        # Base sample around base_delay
        target = self.base_delay * fatigue
        # N-gram speedup inside common runs (burst)
        ngram_mult = current_ngram_multiplier(text, pos)
        target *= ngram_mult

        sample = self._lognormal(target)

        # AR(1) momentum: blend with previous delay
        alpha = self.cfg.momentum
        delay = alpha * self.prev_delay + (1 - alpha) * sample

        # Punctuation trailing delay (the keystroke that WAS the punctuation)
        ch = text[pos]
        if ch in ".!?":
            delay *= 2.3
        elif ch in ",;:":
            delay *= 1.7
        elif ch == "\n":
            delay *= 2.8

        self.prev_delay = delay
        return max(0.008, delay)

    def shift_overhead(self) -> float:
        """Extra time before an uppercase key (shift press)."""
        return self._lognormal(0.055 + 0.04 * self.cfg.randomness, sigma_scale=0.6)

    def inter_word_pause(self, word: str) -> float:
        pause_target = self.base_delay * 2.2
        if word in COMMON_WORDS:
            pause_target *= 0.55
        elif len(word) > 8:
            pause_target *= 1.3
        return self._lognormal(pause_target, sigma_scale=0.9)

    def thinking_pause(self, text: str, pos: int) -> float:
        """Context-aware pause BEFORE typing text[pos]."""
        if pos < 2:
            return 0.0
        r = self.cfg.randomness
        prev = text[pos - 1]
        prev2 = text[pos - 2] if pos >= 2 else ""

        # After sentence end + space.
        if prev == " " and prev2 in ".!?":
            return max(0.35, self._lognormal(self.base_delay * random.uniform(14, 26), 1.2))

        # After clause end + space.
        if prev == " " and prev2 in ",;:":
            if random.random() < 0.38:
                return self._lognormal(self.base_delay * random.uniform(5, 11), 1.0)

        # At the start of a new line.
        if prev == "\n":
            if random.random() < 0.7:
                return max(0.4, self._lognormal(self.base_delay * random.uniform(16, 34), 1.3))

        # Before a conjunction.
        if is_word_boundary(text, pos):
            word = word_at_position(text, pos)
            if word in CONJUNCTIONS and random.random() < 0.4:
                return self._lognormal(self.base_delay * random.uniform(8, 16), 1.1)
            # Rare mid-thought hesitation at a word boundary.
            roll = random.random()
            if roll < 0.05:
                return random.uniform(0.25, 0.7) * (0.5 + r)
            if roll < 0.065:
                return random.uniform(0.8, 1.9) * (0.5 + r)

        return 0.0
