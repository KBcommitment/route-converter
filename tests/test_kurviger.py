import os
import unittest

from route_converter.apple_maps import build_url
from route_converter.parsers import parse_source
from route_converter.simplify import reduce_checkpoints

SAMPLE = os.path.join(
    os.path.dirname(__file__),
    "..",
    "sample",
    "Aandalsnes - Trollstigen - Valldal.kurviger",
)


@unittest.skipUnless(os.path.exists(SAMPLE), "sample .kurviger file not present")
class TestKurvigerEndToEnd(unittest.TestCase):
    def test_parse_real_file(self):
        route = parse_source(SAMPLE)
        self.assertEqual(route.source_format, "kurviger")
        # Dense curvy geometry, not just the planned waypoints.
        self.assertGreater(len(route.checkpoints), 1000)
        # Endpoints match the planned start / destination.
        self.assertAlmostEqual(route.checkpoints[0].lat, 62.5672, places=3)
        self.assertAlmostEqual(route.checkpoints[0].lon, 7.6875, places=3)
        self.assertAlmostEqual(route.checkpoints[-1].lat, 62.3286, places=3)
        self.assertAlmostEqual(route.checkpoints[-1].lon, 7.3462, places=3)

    def test_reduce_and_build_url(self):
        route = parse_source(SAMPLE)
        used = reduce_checkpoints(route.checkpoints, 15)
        self.assertLessEqual(len(used), 15)
        self.assertGreaterEqual(len(used), 2)
        # Start and destination are preserved through reduction.
        self.assertEqual(used[0], route.checkpoints[0])
        self.assertEqual(used[-1], route.checkpoints[-1])

        url = build_url(used)
        self.assertIn("maps.apple.com/directions", url)
        self.assertIn("waypoint=", url)
        self.assertIn("mode=driving", url)


if __name__ == "__main__":
    unittest.main()
