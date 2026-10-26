"""Create public fixtures from explicit equations, never from recorded data.

Run from the repository root: python tools/create_synthetic.py
This intentionally rewrites only the two declared synthetic fixture directories.
"""

import csv
from io import StringIO
import json
import math
from pathlib import Path


def generate() -> dict[str, str]:
    csv_buffer = StringIO(newline="")
    writer = csv.writer(csv_buffer, lineterminator="\n")
    writer.writerow(["lap", "distance_m", "elapsed_s", "speed_kmh", "throttle_pct", "steering_deg"])
    for name in ("A", "B"):
        elapsed = 0.0
        last_speed = None
        for distance in range(0, 1001, 5):
            speed = 112 - 52 * math.exp(-((distance - 230) / 60) ** 2) - 43 * math.exp(-((distance - 690) / 75) ** 2)
            if name == "B":
                speed += 4 * math.exp(-((distance - 300) / 65) ** 2) - 4 * math.exp(-((distance - 610) / 65) ** 2) + 6 * math.exp(-((distance - 775) / 80) ** 2)
            if last_speed is not None:
                elapsed += 2 * 5 / (last_speed + speed) * 3.6
            throttle = max(0, min(100, (speed - 58) * 2.2))
            steering = 66 * math.exp(-((distance - 230) / 48) ** 2) - 58 * math.exp(-((distance - 690) / 58) ** 2)
            if name == "B":
                steering *= .94
            writer.writerow([name, distance, f"{elapsed:.6f}", f"{speed:.6f}", f"{throttle:.6f}", f"{steering:.6f}"])
            last_speed = speed
    states = [{"age_seconds": 0, "race": {"lap": 1, "completed_laps": 0, "sector": 1, "best_lap_sec": None}}]
    best = None
    for completed, duration in enumerate((120.0, 118.8, 119.3, 121.1, 125.0), 1):
        for sector in (2, 3):
            states.append({"age_seconds": 0, "race": {"lap": completed, "completed_laps": completed - 1, "sector": sector,
                                                       "best_lap_sec": best}})
        best = min(best, duration) if best is not None else duration
        states.append({"age_seconds": 0, "race": {"lap": completed + 1, "completed_laps": completed, "sector": 1,
                                                   "last_lap_sec": duration, "best_lap_sec": best}})
    spec = {"synthetic": True, "coordinate_contract": "pre-aligned common route distance, not independently measured odometry",
            "sector_boundaries_m": [0, 340, 700, 1000],
            "corners": [{"name": "합성 코너 1", "center_m": 230}, {"name": "합성 코너 2", "center_m": 690}]}
    metadata = {"synthetic": True, "source": "deterministic equations in tools/create_synthetic.py",
                "contains_recorded_driving_data": False, "contains_gps": False, "contains_vehicle_identifiers": False,
                "telemetry": "two artificial 1000m paths, 5m sampling; time integrated from artificial speed",
                "states": "independent classification scenario; lap times are not telemetry lap A/B times",
                "corner_numbering": "fictional; not an official circuit map", "random_seed": "not used; deterministic"}
    return {"telemetry.csv": csv_buffer.getvalue(),
            "lap_states.jsonl": "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in states),
            "analysis_spec.json": json.dumps(spec, ensure_ascii=False, indent=2) + "\n",
            "metadata.json": json.dumps(metadata, ensure_ascii=False, indent=2) + "\n"}


if __name__ == "__main__":
    root = Path(__file__).resolve().parent.parent
    for destination in (root / "data/synthetic", root / "jev/fixtures"):
        destination.mkdir(parents=True, exist_ok=True)
        for name, content in generate().items():
            (destination / name).write_text(content, encoding="utf-8", newline="")
    print("Synthetic fixtures created; no input data read")
