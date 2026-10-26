import argparse
import json
from pathlib import Path
import sys

from .analysis import compare_laps, read_laps
from .coaching import OfflineCoach
from .reporting import write_report


def replay(path: Path) -> list[dict]:
    coach = OfflineCoach()
    events = []
    with path.open(encoding="utf-8-sig") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError(f"line {line_number}: state must be an object")
            events.extend(coach.observe(row, age_seconds=row.get("age_seconds", 0.0)))
    return events


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="JEV offline synthetic coaching demo; no vehicle or network access")
    sub = parser.add_subparsers(dest="command", required=True)
    demo = sub.add_parser("demo", help="analyze bundled synthetic data")
    demo.add_argument("--output", type=Path, default=Path("build/demo"))
    event_parser = sub.add_parser("replay", help="classify local JSONL states into text events")
    event_parser.add_argument("--input", type=Path, required=True)
    event_parser.add_argument("--output", type=Path, required=True)
    analyze = sub.add_parser("analyze", help="analyze pre-aligned local CSV values")
    analyze.add_argument("--input", type=Path, required=True)
    analyze.add_argument("--spec", type=Path, required=True)
    analyze.add_argument("--reference", required=True)
    analyze.add_argument("--candidate", required=True)
    analyze.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "replay":
            events = replay(args.input)
            write_json(args.output, {"mode": "offline_text_only", "events": events})
            print(f"Wrote {len(events)} events")
            return 0
        synthetic = args.command == "demo"
        if synthetic:
            fixture = Path(__file__).parent / "fixtures"
            args.input, args.spec = fixture / "telemetry.csv", fixture / "analysis_spec.json"
            args.reference, args.candidate = "A", "B"
        spec = json.loads(args.spec.read_text(encoding="utf-8"))
        if not isinstance(spec, dict):
            raise ValueError("analysis spec must be a JSON object")
        laps = read_laps(args.input)
        result = compare_laps(laps, args.reference, args.candidate, spec)
        write_report(args.output, result, laps, synthetic=synthetic)
        if synthetic:
            events = replay(fixture / "lap_states.jsonl")
            write_json(args.output / "coach_events.json", {"synthetic_data": True, "mode": "offline_text_only", "events": events})
        print(f"Created {args.output / 'index.html'}")
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"Input/output error: {exc}", file=sys.stderr)
        return 2
