import math
from pathlib import Path
import tempfile
import unittest

from jev.analysis import Lap, Sample, compare_laps, corner_summary, read_laps
from jev.reporting import svg_chart, write_report

TEST_TEMP = Path(__file__).resolve().parent.parent / "build/test_tmp"
TEST_TEMP.mkdir(parents=True, exist_ok=True)


def constant_lap(name, speed, length=1000):
    # Exact constant-speed travel provides an independent numerical oracle.
    return Lap(name, [Sample(d, d / speed * 3.6, speed, 50, 0) for d in range(0, length + 1, 10)])


class AnalysisTests(unittest.TestCase):
    def setUp(self):
        self.a, self.b = constant_lap("A", 100), constant_lap("B", 120)
        self.spec = {"sector_boundaries_m": [0, 500, 1000], "corners": [{"name": "test", "center_m": 500}]}

    def test_exact_interval_and_sector_times(self):
        result = compare_laps({"A": self.a, "B": self.b}, "A", "B", self.spec)
        self.assertEqual(result["interval_times_seconds"], {"A": 36, "B": 30})
        self.assertEqual([r["delta_seconds"] for r in result["sectors"]], [-3, -3])
        self.assertEqual(result["corners"][0]["delta_passage_seconds"], -.9)

    def test_interpolation_and_no_extrapolation(self):
        self.assertAlmostEqual(self.a.at(15, "elapsed_s"), .54)
        for d in (-.1, 1000.1, math.nan):
            with self.assertRaises(ValueError):
                self.a.at(d, "speed_kmh")

    def test_duplicate_distance_and_time_reversal(self):
        for samples in ([Sample(0, 0, 100, 50, 0), Sample(0, 1, 100, 50, 0)],
                        [Sample(0, 1, 100, 50, 0), Sample(10, 0, 100, 50, 0)]):
            with self.assertRaises(ValueError):
                Lap("bad", samples)

    def test_nonfinite_and_out_of_range_rejected(self):
        for sample in (Sample(10, 1, math.nan, 50, 0), Sample(10, 1, 100, 101, 0), Sample(10, 1, 100, 50, 721)):
            with self.assertRaises(ValueError):
                Lap("bad", [Sample(0, 0, 100, 50, 0), sample])

    def test_invalid_sector_order_and_uncovered_corner(self):
        for spec in ({"sector_boundaries_m": [0, 700, 500]}, {"sector_boundaries_m": [0, 1001]},
                     {"sector_boundaries_m": [0, 1000], "corners": [{"name": "outside", "center_m": 950}]}):
            with self.assertRaises(ValueError):
                compare_laps({"A": self.a, "B": self.b}, "A", "B", spec)

    def test_window_boundary_minimum_is_explicit(self):
        lap = Lap("A", [Sample(d, d / 25, 120 - d / 100, 50, 0) for d in range(0, 1001, 10)])
        summary = corner_summary(lap, 500)
        self.assertTrue(summary["minimum_at_window_boundary"])
        self.assertEqual(summary["window_min_offset_m"], 40)
        self.assertEqual(summary["entry_speed_kmh"], 115.7)
        self.assertEqual(summary["exit_speed_kmh"], 114.2)

    def test_missing_csv_column_fails(self):
        with tempfile.TemporaryDirectory(dir=TEST_TEMP) as temporary:
            p = Path(temporary) / "bad.csv"
            p.write_text("lap,distance_m\nA,0\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                read_laps(p)

    def test_html_labels_are_escaped(self):
        label = '<script>alert("x")</script>'
        bad_label = constant_lap(label, 120)
        result = compare_laps({"A": self.a, label: bad_label}, "A", label, self.spec)
        with tempfile.TemporaryDirectory(dir=TEST_TEMP) as temporary:
            p = Path(temporary)
            write_report(p, result, {"A": self.a, label: bad_label}, synthetic=True)
            html = (p / "index.html").read_text(encoding="utf-8")
            self.assertNotIn("<script>", html)
            self.assertIn("&lt;script&gt;", html)
            self.assertIn("합성 데이터", html)

    def test_graphs_use_two_colored_solid_lines(self):
        svg = svg_chart((self.a, self.b), "speed_kmh", "Speed", "km/h")
        self.assertIn('stroke="#1768b0"', svg)
        self.assertIn('stroke="#ad4600"', svg)
        self.assertNotIn("stroke-dasharray", svg)


if __name__ == "__main__":
    unittest.main()
