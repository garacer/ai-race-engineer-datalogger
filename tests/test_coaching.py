import math
import unittest

from jev.coaching import CoachingPolicy, OfflineCoach


def state(completed=0, sector=1, last=None, best=None, lap=None):
    return {"race": {"lap": lap if lap is not None else completed + 1, "completed_laps": completed,
                     "sector": sector, "last_lap_sec": last, "best_lap_sec": best}}


class CoachingTests(unittest.TestCase):
    def test_startup_does_not_reannounce_existing_lap(self):
        coach = OfflineCoach()
        self.assertEqual(coach.observe(state(6, 2, 123, 120)), [])
        self.assertEqual(coach.observe(state(6, 2, 123, 120)), [])

    def test_first_and_previous_best_before_current_lap(self):
        coach = OfflineCoach()
        coach.observe(state())
        first = coach.observe(state(1, last=120, best=120))[0]
        self.assertEqual(first["type"], "dyn_first")
        self.assertIsNone(first["delta_vs_previous_best_sec"])
        best = coach.observe(state(2, last=119, best=119))[0]
        self.assertEqual(best["previous_best_sec"], 120)
        self.assertEqual(best["delta_vs_previous_best_sec"], -1)
        self.assertEqual(best["type"], "dyn_best")

    def test_delta_boundaries(self):
        for duration, category in ((119.94, "best"), (119.95, "close"), (120.999, "close"),
                                   (121, "moderate"), (122.999, "moderate"), (123, "large")):
            with self.subTest(duration=duration):
                coach = OfflineCoach()
                coach.observe(state(best=120))
                self.assertEqual(coach.observe(state(1, last=duration, best=min(120, duration)))[0]["type"], "dyn_" + category)

    def test_duplicate_and_session_reset(self):
        coach = OfflineCoach()
        coach.observe(state())
        self.assertEqual(len(coach.observe(state(1, last=120, best=120))), 1)
        self.assertEqual(coach.observe(state(1, last=120, best=120)), [])
        self.assertEqual(coach.observe(state()), [])
        self.assertEqual(coach.observe(state(1, last=140, best=140))[0]["type"], "dyn_first")

    def test_missing_laps_do_not_fabricate_completion(self):
        coach = OfflineCoach()
        coach.observe(state())
        self.assertEqual(coach.observe(state(3, last=120, best=120)), [])

    def test_sector_transition_requires_same_lap(self):
        coach = OfflineCoach()
        coach.observe(state())
        self.assertEqual(coach.observe(state(sector=2))[0]["type"], "sector1")
        self.assertEqual(coach.observe(state(sector=3))[0]["type"], "sector2")
        self.assertEqual(coach.observe(state(sector=2, lap=2)), [])

    def test_stale_state_does_not_update_baseline(self):
        coach = OfflineCoach()
        coach.observe(state())
        changed = state(1, last=120, best=120)
        self.assertEqual(coach.observe(changed, age_seconds=6), [])
        self.assertEqual(coach.observe(changed)[0]["type"], "dyn_first")

    def test_invalid_counters_rejected_without_truncating(self):
        for bad in (math.nan, math.inf, -1, 1.9, True, "not-a-number"):
            with self.subTest(bad=bad):
                coach = OfflineCoach()
                coach.observe(state())
                invalid = state(1, last=120, best=120)
                invalid["race"]["completed_laps"] = bad
                self.assertEqual(coach.observe(invalid), [])
                self.assertEqual(coach.observe(state(1, last=120, best=120))[0]["type"], "dyn_first")

    def test_invalid_lap_time_not_spoken(self):
        for bad in (math.nan, math.inf, -1, 0, 901, True, None):
            coach = OfflineCoach()
            coach.observe(state())
            self.assertEqual(coach.observe(state(1, last=bad)), [])

    def test_policy_validation(self):
        for kwargs in ({"max_age_seconds": -1}, {"max_age_seconds": math.inf}, {"best_tolerance_seconds": 1}):
            with self.assertRaises(ValueError):
                CoachingPolicy(**kwargs)


if __name__ == "__main__":
    unittest.main()
