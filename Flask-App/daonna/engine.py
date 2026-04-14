"""Typing engine: orchestrates rhythm, typos, and actuation."""

import random
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

import pyautogui

from . import typos as T
from .rhythm import RhythmConfig, RhythmState


# Disable pyautogui's per-call fail-safe sleep — we control all timing ourselves.
pyautogui.PAUSE = 0


@dataclass
class TypingState:
    running: bool = False
    position: int = 0
    total: int = 0
    started_at: Optional[float] = None
    message: str = ""

    def snapshot(self) -> dict:
        elapsed = (time.time() - self.started_at) if self.started_at else 0.0
        return {
            "running": self.running,
            "position": self.position,
            "total": self.total,
            "progress": (self.position / self.total) if self.total else 0.0,
            "elapsed": elapsed,
            "message": self.message,
        }


class TypingEngine:
    """Single-instance typing controller with cancellation support."""

    def __init__(self):
        self._state = TypingState()
        self._lock = threading.Lock()
        self._cancel = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # ---------------- public API ----------------

    @property
    def state(self) -> TypingState:
        return self._state

    def start(
        self,
        text: str,
        wpm: int,
        randomness: float,
        typo_probability: float,
        momentum: float = 0.45,
        countdown: float = 5.0,
    ) -> bool:
        """Return True if started, False if already running."""
        with self._lock:
            if self._state.running:
                return False
            self._cancel.clear()
            self._state = TypingState(
                running=True,
                position=0,
                total=len(text),
                started_at=time.time(),
                message=f"Starting in {int(countdown)}s...",
            )

        cfg = RhythmConfig(
            wpm=wpm,
            randomness=randomness,
            momentum=momentum,
            fatigue_seed=random.random(),
        )
        self._thread = threading.Thread(
            target=self._run,
            args=(text, cfg, typo_probability, countdown),
            daemon=True,
        )
        self._thread.start()
        return True

    def stop(self) -> None:
        self._cancel.set()

    # ---------------- internals ----------------

    def _sleep(self, duration: float) -> bool:
        """Sleep but check cancel flag every ~20ms. Returns False if cancelled."""
        if duration <= 0:
            return not self._cancel.is_set()
        end = time.time() + duration
        while True:
            if self._cancel.is_set():
                return False
            remaining = end - time.time()
            if remaining <= 0:
                return True
            time.sleep(min(remaining, 0.02))

    def _type_char(self, ch: str, rhythm: RhythmState) -> None:
        """Type a single character, inserting shift overhead for uppercase."""
        if ch.isupper():
            # Shift "press" overhead — we can't time a real shift via pyautogui.write,
            # so simulate by delaying before the write.
            overhead = rhythm.shift_overhead()
            time.sleep(min(overhead, 0.4))
        pyautogui.write(ch)

    def _backspace_burst(self, count: int, rhythm: RhythmState) -> bool:
        """Fire `count` backspaces in a tight burst with mild ramp."""
        # Backspace bursts accelerate slightly then plateau — model with 3 phases.
        base = max(0.025, rhythm.base_delay * 0.35)
        for i in range(count):
            if self._cancel.is_set():
                return False
            pyautogui.press("backspace")
            # Accelerate over the first few, then hold
            factor = 1.25 if i == 0 else (0.9 if i < 3 else 0.75)
            jitter = random.uniform(0.85, 1.15)
            if not self._sleep(base * factor * jitter):
                return False
        return True

    def _run(self, text: str, cfg: RhythmConfig, typo_prob: float, countdown: float) -> None:
        try:
            # ---- countdown window ----
            step = 0.25
            t = 0.0
            while t < countdown:
                if self._cancel.is_set():
                    return
                remaining = max(0, countdown - t)
                self._state.message = f"Focus target window... {remaining:.1f}s"
                time.sleep(step)
                t += step

            self._state.message = "Typing..."
            rhythm = RhythmState(cfg)
            i = 0
            n = len(text)

            while i < n:
                if self._cancel.is_set():
                    break

                # 1. Word-boundary pause
                from .lexicon import is_word_boundary, word_at_position
                if is_word_boundary(text, i):
                    word = word_at_position(text, i)
                    pause = rhythm.inter_word_pause(word)
                    if not self._sleep(pause):
                        break

                # 2. Thinking pause (before this character)
                tp = rhythm.thinking_pause(text, i)
                if tp > 0 and not self._sleep(tp):
                    break

                # 3. Typo?
                typo = T.maybe_typo(text, i, typo_prob)
                if typo is not None:
                    consumed = self._execute_typo(text, i, typo, rhythm)
                    i += consumed
                    self._state.position = i
                    continue

                # 4. Normal keystroke
                self._type_char(text[i], rhythm)
                self._state.position = i + 1

                # 5. Post-keystroke delay (with momentum, fatigue, ngram, punctuation)
                delay = rhythm.keystroke_delay(text, i)
                if not self._sleep(delay):
                    break

                i += 1

            if self._cancel.is_set():
                self._state.message = "Stopped."
            else:
                self._state.message = "Done."
        finally:
            self._state.running = False

    # ---------------- typo execution ----------------

    def _execute_typo(self, text: str, pos: int, typo: T.Typo, rhythm: RhythmState) -> int:
        """Execute a typo + its correction. Returns source chars consumed."""
        plan = T.plan_correction()
        consumed = 1
        typed = 0  # chars actually output (need to backspace this many + extras)

        if typo.kind == T.ADJACENT or typo.kind == T.MIRROR:
            pyautogui.write(str(typo.data))
            typed = 1
        elif typo.kind == T.TRANSPOSITION:
            a, b = typo.data  # type: ignore
            pyautogui.write(a)
            if not self._sleep(rhythm.keystroke_delay(text, pos) * 0.55):
                return consumed
            pyautogui.write(b)
            typed = 2
            consumed = 2
        elif typo.kind == T.DOUBLE:
            pyautogui.write(str(typo.data))
            if not self._sleep(rhythm.keystroke_delay(text, pos) * 0.45):
                return consumed
            pyautogui.write(str(typo.data))
            typed = 2
        elif typo.kind == T.SKIP:
            typed = 0  # nothing output

        if self._cancel.is_set():
            return consumed

        # Uncorrected: accept the typo and move on.
        if plan.style == T.IGNORE:
            return consumed

        # SKIP typos: always "correct" by typing the character we missed.
        if typo.kind == T.SKIP and plan.style != T.IGNORE:
            # Brief hesitation, then type the correct char we skipped
            if not self._sleep(rhythm.keystroke_delay(text, pos) * 1.3):
                return consumed
            self._type_char(text[pos], rhythm)
            return consumed

        # Type extra source chars before noticing (DELAYED style).
        extra_typed = 0
        src = pos + consumed
        for _ in range(max(0, plan.notice_after)):
            if src >= len(text) or self._cancel.is_set():
                break
            if not self._sleep(rhythm.keystroke_delay(text, src - 1)):
                return consumed
            self._type_char(text[src], rhythm)
            extra_typed += 1
            src += 1
            consumed += 1
            self._state.position = pos + consumed

        if self._cancel.is_set():
            return consumed

        # Realization pause — style-dependent.
        if plan.style == T.STARE:
            stare = random.uniform(0.45, 1.2)
            if not self._sleep(stare):
                return consumed
        elif plan.style == T.DELAYED:
            stare = random.uniform(0.35, 0.9)
            if not self._sleep(stare):
                return consumed
        else:  # IMMEDIATE
            if not self._sleep(rhythm.base_delay * random.uniform(0.8, 1.6)):
                return consumed

        # Burst-backspace everything we typed (typo + any extras).
        total_to_delete = typed + extra_typed
        if not self._backspace_burst(total_to_delete, rhythm):
            return consumed

        # Small pre-retype pause.
        if not self._sleep(rhythm.base_delay * random.uniform(0.6, 1.2)):
            return consumed

        # Retype the correct sequence.
        end = min(pos + consumed, len(text))
        for j in range(pos, end):
            if self._cancel.is_set():
                return consumed
            self._type_char(text[j], rhythm)
            if j + 1 < end:
                if not self._sleep(rhythm.keystroke_delay(text, j) * 0.9):
                    return consumed

        return consumed
