import io
import json
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from route_converter.cli import main

SAMPLE = str(
    Path(__file__).resolve().parent.parent
    / "sample"
    / "Aandalsnes - Trollstigen - Valldal.kurviger"
)


def run(*argv) -> dict:
    buf = io.StringIO()
    with redirect_stdout(buf):
        main([SAMPLE, "--json", *argv])
    return json.loads(buf.getvalue())


class TestCli(unittest.TestCase):
    def test_default_route_is_navigable(self):
        """No source= — Apple Maps only offers "Go" from the current location."""
        out = run()
        self.assertEqual(out["origin"], "current-location")
        self.assertNotIn("source=", out["url"])
        self.assertIn("destination=", out["url"])

    def test_current_location_reserves_a_stop(self):
        # The device's location is itself one of Apple's ~15 stops, so only
        # max_stops - 1 points come from the route.
        self.assertEqual(run("--max-stops", "15")["checkpoints_used"], 14)
        self.assertEqual(run("--max-stops", "8")["checkpoints_used"], 7)
        # Pinning the origin spends no stop on the current location.
        self.assertEqual(
            run("--max-stops", "15", "--source-at-start")["checkpoints_used"], 15
        )

    def test_source_at_start_pins_origin(self):
        out = run("--source-at-start")
        self.assertEqual(out["origin"], "route-start")
        self.assertIn("source=", out["url"])

    def test_navigation_starts_by_default(self):
        """start= is what actually begins turn-by-turn; a preview link doesn't."""
        self.assertIn("start=0", run()["url"])
        self.assertIn("start=45", run("--start", "45")["url"])

    def test_no_start_makes_a_preview(self):
        out = run("--no-start")
        self.assertNotIn("start=", out["url"])
        self.assertIsNone(out["start_delay"])

    def test_max_stops_too_small(self):
        with self.assertRaises(SystemExit):
            run("--max-stops", "1")


if __name__ == "__main__":
    unittest.main()
