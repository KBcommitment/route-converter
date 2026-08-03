import unittest

from route_converter.apple_maps import build_url
from route_converter.models import Checkpoint


class TestAppleMaps(unittest.TestCase):
    def test_multi_stop_unified_format(self):
        pts = [
            Checkpoint(62.57, 7.69),
            Checkpoint(62.45, 7.66),
            Checkpoint(62.33, 7.35),
        ]
        url = build_url(pts, mode="drive")
        self.assertTrue(url.startswith("https://maps.apple.com/directions?"))
        self.assertIn("source=62.570000,7.690000", url)
        self.assertIn("waypoint=62.450000,7.660000", url)
        self.assertIn("destination=62.330000,7.350000", url)
        self.assertIn("mode=driving", url)
        # order must be source -> waypoint -> destination
        self.assertLess(url.index("source="), url.index("waypoint="))
        self.assertLess(url.index("waypoint="), url.index("destination="))

    def test_two_points_have_no_waypoint(self):
        url = build_url([Checkpoint(1, 2), Checkpoint(3, 4)])
        self.assertIn("source=1.000000,2.000000", url)
        self.assertIn("destination=3.000000,4.000000", url)
        self.assertNotIn("waypoint=", url)

    def test_from_current_omits_source(self):
        # Omitting source is what makes the route navigable: Apple Maps only
        # offers "Go" (and CarPlay turn-by-turn) from the current location.
        url = build_url(
            [Checkpoint(1, 2), Checkpoint(3, 4), Checkpoint(5, 6)],
            from_current=True,
        )
        self.assertNotIn("source=", url)
        self.assertIn("waypoint=1.000000,2.000000", url)
        self.assertIn("destination=5.000000,6.000000", url)

    def test_start_delay(self):
        pts = [Checkpoint(1, 2), Checkpoint(3, 4)]
        self.assertIn("start=0", build_url(pts, start=0))
        self.assertIn("start=30", build_url(pts, start=30))
        self.assertNotIn("start=", build_url(pts))

    def test_negative_start_raises(self):
        with self.assertRaises(ValueError):
            build_url([Checkpoint(1, 2), Checkpoint(3, 4)], start=-1)

    def test_single_point(self):
        url = build_url([Checkpoint(5, 6)])
        self.assertNotIn("source=", url)
        self.assertNotIn("waypoint=", url)
        self.assertIn("destination=5.000000,6.000000", url)

    def test_modes(self):
        a, b = Checkpoint(1, 2), Checkpoint(3, 4)
        self.assertIn("mode=walking", build_url([a, b], mode="walk"))
        self.assertIn("mode=transit", build_url([a, b], mode="transit"))
        self.assertIn("mode=cycling", build_url([a, b], mode="cycle"))

    def test_avoid(self):
        url = build_url([Checkpoint(1, 2), Checkpoint(3, 4)], avoid=["highways", "tolls"])
        self.assertIn("avoid=highways,tolls", url)

    def test_maps_scheme(self):
        url = build_url([Checkpoint(1, 2), Checkpoint(3, 4)], scheme="maps")
        self.assertTrue(url.startswith("maps://directions?"))

    def test_unknown_mode_raises(self):
        with self.assertRaises(ValueError):
            build_url([Checkpoint(1, 2)], mode="fly")

    def test_unknown_avoid_raises(self):
        with self.assertRaises(ValueError):
            build_url([Checkpoint(1, 2), Checkpoint(3, 4)], avoid=["volcanoes"])

    def test_empty_raises(self):
        with self.assertRaises(ValueError):
            build_url([])


if __name__ == "__main__":
    unittest.main()
