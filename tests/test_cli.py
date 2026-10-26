import contextlib
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest

from jev.cli import main, replay
from tools.create_synthetic import generate


ROOT = Path(__file__).resolve().parent.parent
TEST_TEMP = ROOT / "build/test_tmp"
TEST_TEMP.mkdir(parents=True, exist_ok=True)


class DemoIntegrationTests(unittest.TestCase):
    def test_fixtures_are_reproducible_and_public_copies_match(self):
        for name, content in generate().items():
            for folder in (ROOT / "data/synthetic", ROOT / "jev/fixtures"):
                self.assertEqual((folder / name).read_text(encoding="utf-8"), content)

    def test_state_fixture_covers_all_categories(self):
        events = replay(ROOT / "data/synthetic/lap_states.jsonl")
        lap_events = [event for event in events if event["type"].startswith("dyn_")]
        self.assertEqual([e["type"] for e in lap_events], ["dyn_first", "dyn_best", "dyn_close", "dyn_moderate", "dyn_large"])
        self.assertEqual(len(events), 15)

    def test_complete_demo_outputs(self):
        with tempfile.TemporaryDirectory(dir=TEST_TEMP) as temporary:
            output = Path(temporary) / "demo"
            with contextlib.redirect_stdout(StringIO()):
                self.assertEqual(main(["demo", "--output", str(output)]), 0)
            required = {"index.html", "summary.json", "coach_events.json", "speed.svg", "throttle.svg", "steering.svg", "delta.svg"}
            self.assertEqual({p.name for p in output.iterdir()}, required)
            report = json.loads((output / "summary.json").read_text(encoding="utf-8"))
            self.assertTrue(report["synthetic_data"])
            self.assertEqual(len(report["corners"]), 2)
            total_delta = report["interval_times_seconds"]["B"] - report["interval_times_seconds"]["A"]
            self.assertAlmostEqual(sum(s["delta_seconds"] for s in report["sectors"]), total_delta, places=5)

    def test_cli_bad_input_returns_nonzero(self):
        with tempfile.TemporaryDirectory(dir=TEST_TEMP) as temporary, contextlib.redirect_stderr(StringIO()):
            self.assertEqual(main(["replay", "--input", str(Path(temporary) / "missing.jsonl"), "--output", str(Path(temporary) / "out.json")]), 2)


if __name__ == "__main__":
    unittest.main()
