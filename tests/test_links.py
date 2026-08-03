import unittest

from route_converter.parsers.links import parse_google_maps_link

# Real-world shape: raw-coordinate start, named destination, and the resolved
# destination coordinate in the data= payload as !1d<lng>!2d<lat>.
FULL = (
    "https://www.google.com/maps/dir/62.5672,7.6875/"
    "Trollstigen+utsiktspunkt/"
    "@62.45,7.6,11z/"
    "data=!3m1!1e3!4m12!1m5!1m1!1s0x0:0x0"
    "!2m2!1d7.6664!2d62.4566!3e0"
)


class TestGoogleLink(unittest.TestCase):
    def test_named_destination_filled_from_data(self):
        route = parse_google_maps_link(FULL)
        self.assertEqual(route.source_format, "google-maps-link")
        self.assertEqual(len(route.checkpoints), 2)
        # start from /dir/ coordinate
        self.assertAlmostEqual(route.checkpoints[0].lat, 62.5672, places=4)
        self.assertAlmostEqual(route.checkpoints[0].lon, 7.6875, places=4)
        # destination filled from !1d(lng)!2d(lat)
        self.assertAlmostEqual(route.checkpoints[1].lat, 62.4566, places=4)
        self.assertAlmostEqual(route.checkpoints[1].lon, 7.6664, places=4)

    def test_all_coordinate_dir_segments(self):
        url = "https://www.google.com/maps/dir/62.5,7.7/62.4,7.6/62.3,7.4/"
        route = parse_google_maps_link(url)
        self.assertEqual(len(route.checkpoints), 3)
        self.assertAlmostEqual(route.checkpoints[1].lat, 62.4, places=4)

    def test_unparseable_raises(self):
        with self.assertRaises(ValueError):
            parse_google_maps_link("https://www.google.com/maps/@62.5,7.7,12z")


if __name__ == "__main__":
    unittest.main()
