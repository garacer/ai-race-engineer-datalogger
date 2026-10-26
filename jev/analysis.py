"""Numerical comparisons for already aligned, explicitly named route distances."""

from bisect import bisect_left
import csv
from dataclasses import dataclass
import math
from pathlib import Path
from typing import Any, Iterable


FIELDS = ("distance_m", "elapsed_s", "speed_kmh", "throttle_pct", "steering_deg")


@dataclass(frozen=True)
class Sample:
    distance_m: float
    elapsed_s: float
    speed_kmh: float
    throttle_pct: float
    steering_deg: float


def finite(value: Any, label: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{label}: boolean is not a measurement")
    try:
        number = float(value)
    except (ValueError, TypeError, OverflowError) as exc:
        raise ValueError(f"{label}: expected a finite number") from exc
    if not math.isfinite(number):
        raise ValueError(f"{label}: expected a finite number")
    return number


class Lap:
    def __init__(self, name: str, samples: Iterable[Sample]) -> None:
        self.name = name
        self.samples = list(samples)
        if len(self.samples) < 2:
            raise ValueError(f"lap {name}: at least two samples required")
        previous = None
        for row in self.samples:
            for field in FIELDS:
                finite(getattr(row, field), field)
            if row.distance_m < 0 or row.elapsed_s < 0:
                raise ValueError(f"lap {name}: distance/time must be nonnegative")
            if not 0 <= row.speed_kmh <= 350 or not 0 <= row.throttle_pct <= 100 or not -720 <= row.steering_deg <= 720:
                raise ValueError(f"lap {name}: speed/throttle/steering outside declared range")
            if previous and (row.distance_m <= previous.distance_m or row.elapsed_s <= previous.elapsed_s):
                raise ValueError(f"lap {name}: distance and elapsed time must strictly increase")
            previous = row
        self.distances = [row.distance_m for row in self.samples]

    def at(self, distance: float, field: str) -> float:
        if field not in FIELDS:
            raise ValueError(f"unsupported field: {field}")
        distance = finite(distance, "distance")
        if not self.distances[0] <= distance <= self.distances[-1]:
            raise ValueError(f"lap {self.name}: requested distance outside coverage")
        index = bisect_left(self.distances, distance)
        if index == 0 or self.distances[index] == distance:
            return getattr(self.samples[index], field)
        left, right = self.samples[index - 1:index + 1]
        fraction = (distance - left.distance_m) / (right.distance_m - left.distance_m)
        return getattr(left, field) + fraction * (getattr(right, field) - getattr(left, field))

    def passage_time(self, start: float, end: float) -> float:
        if end <= start:
            raise ValueError("interval end must exceed start")
        return self.at(end, "elapsed_s") - self.at(start, "elapsed_s")


def read_laps(path: Path) -> dict[str, Lap]:
    grouped: dict[str, list[Sample]] = {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not {"lap", *FIELDS}.issubset(reader.fieldnames or []):
            raise ValueError("CSV requires lap," + ",".join(FIELDS))
        for line_number, row in enumerate(reader, start=2):
            name = (row.get("lap") or "").strip()
            if not name or len(name) > 40:
                raise ValueError(f"line {line_number}: invalid lap label")
            values = [finite(row.get(field), f"line {line_number} {field}") for field in FIELDS]
            grouped.setdefault(name, []).append(Sample(*values))
    if not grouped:
        raise ValueError("CSV has no samples")
    return {name: Lap(name, rows) for name, rows in grouped.items()}


def corner_summary(lap: Lap, center: float) -> dict[str, Any]:
    center = finite(center, "corner center")
    lo, hi = center - 40, center + 40
    candidates = [(lo, lap.at(lo, "speed_kmh")), (hi, lap.at(hi, "speed_kmh"))]
    candidates += [(r.distance_m, r.speed_kmh) for r in lap.samples if lo < r.distance_m < hi]
    min_at, minimum = min(candidates, key=lambda pair: pair[1])
    return {
        "entry_speed_kmh": round(lap.at(center - 70, "speed_kmh"), 3),
        "window_min_speed_kmh": round(minimum, 3),
        "window_min_offset_m": round(min_at - center, 3),
        "minimum_at_window_boundary": abs(min_at - lo) < 1e-6 or abs(min_at - hi) < 1e-6,
        "exit_speed_kmh": round(lap.at(center + 80, "speed_kmh"), 3),
        "passage_time_seconds": round(lap.passage_time(center - 70, center + 80), 6),
    }


def compare_laps(laps: dict[str, Lap], reference: str, candidate: str, spec: dict[str, Any]) -> dict[str, Any]:
    if reference == candidate or reference not in laps or candidate not in laps:
        raise ValueError("reference and candidate must identify two distinct existing laps")
    a, b = laps[reference], laps[candidate]
    lo, hi = max(a.distances[0], b.distances[0]), min(a.distances[-1], b.distances[-1])
    if hi <= lo:
        raise ValueError("laps have no common distance interval")
    sectors = spec.get("sector_boundaries_m")
    if not isinstance(sectors, list) or len(sectors) < 2:
        raise ValueError("spec needs at least two sector boundaries")
    boundaries = [finite(value, "sector boundary") for value in sectors]
    if any(right <= left for left, right in zip(boundaries, boundaries[1:])) or boundaries[0] < lo or boundaries[-1] > hi:
        raise ValueError("sector boundaries must strictly increase within common coverage")
    result: dict[str, Any] = {
        "schema_version": 1,
        "reference_lap": reference, "candidate_lap": candidate,
        "alignment": "pre-aligned common route distance; no GPS projection performed",
        "common_coverage_m": [lo, hi],
        "comparison_interval_m": [boundaries[0], boundaries[-1]],
        "delta_convention": "candidate minus reference; negative is less elapsed time",
        "analysis_windows_m": {"entry": -70, "minimum": [-40, 40], "exit": 80},
        "interval_times_seconds": {}, "sectors": [], "corners": [],
    }
    for name, lap in ((reference, a), (candidate, b)):
        result["interval_times_seconds"][name] = round(lap.passage_time(boundaries[0], boundaries[-1]), 6)
    for index, (start, end) in enumerate(zip(boundaries, boundaries[1:]), start=1):
        ta, tb = a.passage_time(start, end), b.passage_time(start, end)
        result["sectors"].append({"sector": index, "start_m": start, "end_m": end,
                                  "reference_seconds": round(ta, 6), "candidate_seconds": round(tb, 6),
                                  "delta_seconds": round(tb - ta, 6)})
    names = set()
    corners = spec.get("corners", [])
    if not isinstance(corners, list):
        raise ValueError("corners must be a list")
    for corner in corners:
        if not isinstance(corner, dict):
            raise ValueError("each corner must be an object")
        name = str(corner.get("name", "")).strip()
        if not name or name in names or len(name) > 60:
            raise ValueError("corner labels must be unique nonempty strings up to 60 characters")
        names.add(name)
        center = finite(corner.get("center_m"), "corner center")
        if center - 70 < lo or center + 80 > hi:
            raise ValueError(f"corner {name}: full analysis window lacks common coverage")
        ma, mb = corner_summary(a, center), corner_summary(b, center)
        result["corners"].append({"name": name, "center_m": center, "reference": ma, "candidate": mb,
                                  "delta_passage_seconds": round(mb["passage_time_seconds"] - ma["passage_time_seconds"], 6)})
    return result
