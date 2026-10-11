"""Combines rules + optional LLM into one stable risk level for a speaker's turns."""

import time
from collections import deque
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass

from app.models.protocol import ScamAlert
from app.services.scam.llm import LlmClassifier, LlmVerdict
from app.services.scam.rules import score_rules

LEVELS = ("none", "suspicious", "high")


@dataclass(frozen=True)
class ShieldConfig:
    window_turns: int = 5
    suspicious_at: int = 40  # enter yellow
    high_at: int = 70  # enter red
    suspicious_exit: int = 30  # to leave yellow, risk must fall below this...
    high_exit: int = 60  # ...and below this to leave red
    exit_evals: int = 2  # ...on this many consecutive evaluations
    llm_min_interval_s: float = 15.0
    llm_max_calls: int = 20  # per shield (one call direction)
    llm_trigger_risk: int = 20  # rules risk that makes the LLM worth asking
    llm_periodic_turns: int = 6  # otherwise ask once every N turns as a safety net
    llm_fresh_turns: int = 6  # a verdict is trusted for this many turns
    breaker_failures: int = 3  # consecutive LLM failures that pause it
    breaker_pause_s: float = 60.0


class ScamShield:
    """One shield per speaker: it watches that speaker's turns for the listener's benefit."""

    def __init__(
        self,
        cfg: ShieldConfig | None = None,
        llm: LlmClassifier | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.cfg = cfg or ShieldConfig()
        self._llm = llm
        self._clock = clock
        self._turns: deque[str] = deque(maxlen=self.cfg.window_turns)
        self.level = "none"
        self.max_level = "none"
        self._low_evals = 0
        self._last_sent: tuple[str, str] = ("none", "none")
        self._held: tuple[str, list[str]] = ("none", [])
        # LLM state
        self._turn_no = 0
        self._llm_calls = 0
        self._llm_failures = 0
        self._llm_paused_until = 0.0
        self._last_llm_at = float("-inf")
        self._last_llm_turn = 0
        self._verdict: LlmVerdict | None = None
        self._verdict_turn = 0

    @property
    def llm_enabled(self) -> bool:
        return self._llm is not None

    # ---- scoring ----
    def _combine(self, rules_risk: int) -> int:
        v = self._verdict
        if v is None or self._turn_no - self._verdict_turn > self.cfg.llm_fresh_turns:
            return rules_risk
        # The LLM can raise suspicion but never lower what the rules already found, so a caller
        # who talks the model into saying "safe" cannot switch the shield off.
        return max(rules_risk, round(0.5 * rules_risk + 0.5 * v.risk))

    def _target(self, risk: int) -> str:
        if risk >= self.cfg.high_at:
            return "high"
        if risk >= self.cfg.suspicious_at:
            return "suspicious"
        return "none"

    def _update_level(self, risk: int) -> None:
        """Hysteresis: rise immediately, fall only after `exit_evals` clearly lower readings."""
        target = self._target(risk)
        if LEVELS.index(target) >= LEVELS.index(self.level):
            self.level = target
            self._low_evals = 0
        else:
            exit_at = self.cfg.high_exit if self.level == "high" else self.cfg.suspicious_exit
            self._low_evals = self._low_evals + 1 if risk < exit_at else 0
            if self._low_evals >= self.cfg.exit_evals:
                self.level = target
                self._low_evals = 0
        if LEVELS.index(self.level) > LEVELS.index(self.max_level):
            self.max_level = self.level

    def _alert(
        self, rules_risk: int, risk: int, categories: dict[str, int], reasons: list[str]
    ) -> ScamAlert | None:
        top = max(categories, key=lambda c: categories[c]) if categories else "none"
        v = self._verdict
        if v is not None and v.category != "none" and v.risk > rules_risk:
            top = v.category
            reasons = [*v.reasons_hinglish, *reasons]
        if self.level != "none":
            # While a level is merely being held by hysteresis, keep what justified it.
            if LEVELS.index(self._target(risk)) >= LEVELS.index(self.level):
                self._held = (top, reasons)
            else:
                top, reasons = self._held
        key = (self.level, top if self.level != "none" else "none")
        if key == self._last_sent:
            return None
        self._last_sent = key
        return ScamAlert(
            level=self.level,
            risk=risk,
            category=top,
            reasons_hinglish=list(dict.fromkeys(reasons))[:3] if self.level != "none" else [],
        )

    def _evaluate(self) -> tuple[int, ScamAlert | None]:
        res = score_rules(list(self._turns))
        risk = self._combine(res.risk)
        self._update_level(risk)
        return res.risk, self._alert(res.risk, risk, res.categories, res.reasons())

    # ---- LLM gating ----
    def _should_ask_llm(self, rules_risk: int) -> bool:
        c = self.cfg
        now = self._clock()
        if self._llm is None or self._llm_calls >= c.llm_max_calls:
            return False
        if now < self._llm_paused_until or now - self._last_llm_at < c.llm_min_interval_s:
            return False
        return (
            rules_risk >= c.llm_trigger_risk
            or self._turn_no - self._last_llm_turn >= c.llm_periodic_turns
        )

    async def _ask_llm(self) -> None:
        assert self._llm is not None
        self._llm_calls += 1
        self._last_llm_at = self._clock()
        self._last_llm_turn = self._turn_no
        verdict = await self._llm.classify(list(self._turns))
        if verdict is None:
            self._llm_failures += 1
            if self._llm_failures >= self.cfg.breaker_failures:
                self._llm_paused_until = self._clock() + self.cfg.breaker_pause_s
                self._llm_failures = 0
            return
        self._llm_failures = 0
        self._verdict, self._verdict_turn = verdict, self._turn_no

    async def on_turn(self, text: str) -> AsyncIterator[ScamAlert]:
        """Feed one finished turn. Yields 0-2 alerts: first from rules (instant), then again if
        the LLM changes the picture. Never raises."""
        if not text.strip():
            return
        self._turns.append(text)
        self._turn_no += 1
        rules_risk, alert = self._evaluate()
        if alert:
            yield alert
        if self._should_ask_llm(rules_risk):
            await self._ask_llm()
            _, alert = self._evaluate()
            if alert:
                yield alert
