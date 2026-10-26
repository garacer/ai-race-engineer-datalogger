"""Pure state-to-text classifier, adapted from the JEV prototype's lap policy.

The public core additionally rejects nonfinite values and resets/jumps. It does
not watch files, run a service, synthesize speech or access a device.
"""

from dataclasses import dataclass
import math
from typing import Any, Mapping


PHRASES = {
    "first": "첫 번째 유효 랩을 완료했습니다.",
    "best": "좋습니다. 이전 베스트보다 빨라졌습니다.",
    "close": "이전 베스트와 1초 미만 차이입니다.",
    "moderate": "이전 베스트보다 1초 이상 3초 미만 느립니다.",
    "large": "이전 베스트보다 3초 이상 느립니다. 주행 상황을 함께 확인하세요.",
}


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        value = float(value)
    except (ValueError, TypeError, OverflowError):
        return None
    return value if math.isfinite(value) else None


def _counter(value: Any, minimum: int, maximum: int) -> int | None:
    value = _number(value)
    if value is None or not value.is_integer() or not minimum <= value <= maximum:
        return None
    return int(value)


def _lap_time(value: Any) -> float | None:
    value = _number(value)
    return value if value is not None and 20 <= value <= 900 else None


@dataclass(frozen=True)
class CoachingPolicy:
    max_age_seconds: float = 5.0
    best_tolerance_seconds: float = 0.05

    def __post_init__(self) -> None:
        if not math.isfinite(self.max_age_seconds) or self.max_age_seconds < 0:
            raise ValueError("max_age_seconds must be finite and nonnegative")
        if not math.isfinite(self.best_tolerance_seconds) or not 0 <= self.best_tolerance_seconds < 1:
            raise ValueError("best_tolerance_seconds must be in [0, 1)")


class OfflineCoach:
    def __init__(self, policy: CoachingPolicy | None = None) -> None:
        self.policy = policy or CoachingPolicy()
        self.previous: tuple[int, int, int] | None = None
        self.previous_best: float | None = None

    def observe(self, state: Mapping[str, Any], *, age_seconds: float = 0.0) -> list[dict[str, Any]]:
        age = _number(age_seconds)
        if age is None or age < 0 or age > self.policy.max_age_seconds:
            return []
        if not isinstance(state, Mapping) or not isinstance(state.get("race"), Mapping):
            return []
        race = state["race"]
        lap = _counter(race.get("lap"), 1, 10001)
        completed = _counter(race.get("completed_laps"), 0, 10000)
        sector = _counter(race.get("sector"), 1, 3)
        if lap is None or completed is None or sector is None:
            return []
        current = (lap, completed, sector)
        best = _lap_time(race.get("best_lap_sec"))
        if self.previous is None:
            self.previous, self.previous_best = current, best
            return []

        prev_lap, prev_completed, prev_sector = self.previous
        prior_best = self.previous_best
        self.previous = current
        if completed < prev_completed or completed - prev_completed > 1:
            # A new session or missed laps establish a new baseline, not fake events.
            self.previous_best = best
            return []

        events: list[dict[str, Any]] = []
        if completed == prev_completed + 1:
            last = _lap_time(race.get("last_lap_sec"))
            if last is not None:
                delta = round(last - prior_best, 3) if prior_best is not None else None
                if delta is None:
                    category = "first"
                elif delta < -self.policy.best_tolerance_seconds:
                    category = "best"
                elif delta < 1:
                    category = "close"
                elif delta < 3:
                    category = "moderate"
                else:
                    category = "large"
                events.append({
                    "type": "dyn_" + category,
                    "completed_laps": completed,
                    "last_lap_sec": last,
                    "previous_best_sec": prior_best,
                    "delta_vs_previous_best_sec": delta,
                    "voice_text": PHRASES[category],
                })
                self.previous_best = min(v for v in (prior_best, best, last) if v is not None)
        elif lap == prev_lap:
            if (prev_sector, sector) in ((1, 2), (2, 3)):
                events.append({"type": f"sector{prev_sector}", "lap": lap,
                               "voice_text": f"{prev_sector}번 섹터를 통과했습니다."})
        if not events and best is not None:
            self.previous_best = min(v for v in (prior_best, best) if v is not None)
        return events
