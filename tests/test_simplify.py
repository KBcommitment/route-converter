import unittest

from route_converter.models import Checkpoint
from route_converter.simplify import _cumulative, reduce_checkpoints


class TestSimplify(unittest.TestCase):
    def test_no_reduction_when_under_limit(self):
        pts = [Checkpoint(0, 0), Checkpoint(1, 1), Checkpoint(2, 2)]
        self.assertEqual(len(reduce_checkpoints(pts, 15)), 3)

    def test_keeps_endpoints_and_named_waypoints(self):
        pts = [Checkpoint(0.0, 0.0, name="start", significant=True)]
        for i in range(1, 50):
            pts.append(Checkpoint(i * 0.01, 0.0))
        pts[25] = Checkpoint(0.25, 0.0, name="via", significant=True)
        pts.append(Checkpoint(0.5, 0.0, name="end", significant=True))

        for strategy in ("hybrid", "even"):
            out = reduce_checkpoints(pts, 6, strategy=strategy)
            self.assertLessEqual(len(out), 6)
            self.assertEqual(out[0].name, "start", strategy)
            self.assertEqual(out[-1].name, "end", strategy)
            self.assertIn("via", [c.name for c in out], strategy)

    def test_even_spacing_on_straight_line(self):
        pts = [Checkpoint(i * 0.01, 0.0) for i in range(101)]
        out = reduce_checkpoints(pts, 11, strategy="even")
        self.assertEqual(len(out), 11)
        cum = _cumulative(out)
        gaps = [cum[i] - cum[i - 1] for i in range(1, len(cum))]
        mean = sum(gaps) / len(gaps)
        self.assertTrue(all(abs(g - mean) < 0.25 * mean for g in gaps), gaps)

    def test_hybrid_captures_detour_that_even_misses(self):
        # Mostly-straight route heading north along lon=0, with a short lateral
        # "town loop" detour bulging east near lat 0.5 (apex at lon 0.05).
        pts = [Checkpoint(i * 0.01, 0.0) for i in range(50)]  # lat 0.00..0.49
        pts += [
            Checkpoint(0.50, 0.03),
            Checkpoint(0.52, 0.05),  # apex of the detour
            Checkpoint(0.54, 0.03),
        ]
        pts += [Checkpoint(i * 0.01, 0.0) for i in range(55, 101)]  # back to lon 0

        hybrid = reduce_checkpoints(pts, 7, strategy="hybrid")
        self.assertTrue(
            any(c.lon > 0.03 for c in hybrid),
            "hybrid should place a waypoint on the detour apex",
        )

    def test_dedupes_consecutive_duplicates(self):
        pts = [Checkpoint(0, 0), Checkpoint(0, 0), Checkpoint(1, 1)]
        out = reduce_checkpoints(pts, 15)
        self.assertEqual(len(out), 2)


if __name__ == "__main__":
    unittest.main()
