import unittest

from route_converter.parsers.polyline import decode


class TestPolyline(unittest.TestCase):
    def test_2d_classic_example(self):
        # Canonical Google example.
        pts = decode("_p~iF~ps|U_ulLnnqC_mqNvxq`@")
        self.assertEqual(len(pts), 3)
        self.assertAlmostEqual(pts[0][0], 38.5, places=4)
        self.assertAlmostEqual(pts[0][1], -120.2, places=4)
        self.assertAlmostEqual(pts[2][0], 43.252, places=3)
        self.assertAlmostEqual(pts[2][1], -126.453, places=3)

    def test_3d_elevation_snapped_waypoints(self):
        # 3-D (elevation=true) encoding of the sample route's endpoints.
        enc = "_d{|J{m|m@g^frm@btaAg^"
        pts = decode(enc, with_elevation=True)
        self.assertEqual(len(pts), 2)
        self.assertAlmostEqual(pts[0][0], 62.5672, places=4)
        self.assertAlmostEqual(pts[0][1], 7.6875, places=4)
        self.assertAlmostEqual(pts[1][0], 62.3286, places=4)
        self.assertAlmostEqual(pts[1][1], 7.3462, places=4)

    def test_3d_decoded_as_2d_is_wrong(self):
        # Guards the elevation-detection: the same string decoded as 2D must
        # NOT yield the correct 2-point result.
        enc = "_d{|J{m|m@g^frm@btaAg^"
        pts2d = decode(enc, with_elevation=False)
        self.assertNotEqual(len(pts2d), 2)


if __name__ == "__main__":
    unittest.main()
