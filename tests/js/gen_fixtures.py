"""Generate golden fixtures for the JS port from the Python reference.

Runs the CLI's --json output for a spread of inputs (real .kurviger samples,
synthetic GPX/KML/KMZ, share links) and stores input + expected output pairs
in fixtures/. Re-run after changing the Python package:

    python3 tests/js/gen_fixtures.py
"""
from __future__ import annotations

import base64
import io
import json
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).resolve().parent / "fixtures"

OUTBOUND = ROOT / "sample" / "Aandalsnes - Trollstigen - Valldal.kurviger"
RETURN = ROOT / "sample" / "Aandalsnes - Trollstigen - Valldal - return.kurviger"

GPX_TRACK = """<?xml version="1.0" encoding="UTF-8"?>
<gpx xmlns="http://www.topografix.com/GPX/1/1" version="1.1" creator="test">
  <metadata><name>Track &amp; Cafe</name></metadata>
  <wpt lat="62.450" lon="7.660"><name>Cafe stop</name></wpt>
  <trk><name>Test Track</name><trkseg>
    <trkpt lat="62.350" lon="7.560"/>
    <trkpt lat="62.370" lon="7.580"/>
    <trkpt lat="62.390" lon="7.600"/>
    <trkpt lat="62.410" lon="7.620"/>
    <trkpt lat="62.430" lon="7.640"/>
    <trkpt lat="62.450" lon="7.660"/>
    <trkpt lat="62.470" lon="7.680"/>
    <trkpt lat="62.490" lon="7.700"/>
    <trkpt lat="62.510" lon="7.720"/>
    <trkpt lat="62.530" lon="7.740"/>
  </trkseg></trk>
</gpx>
"""

GPX_ROUTE = """<?xml version="1.0" encoding="UTF-8"?>
<gpx xmlns="http://www.topografix.com/GPX/1/1" version="1.1" creator="test">
  <rte><name>Planned Route</name>
    <rtept lat="62.250" lon="7.460"><name>Start</name></rtept>
    <rtept lat="62.300" lon="7.510"/>
    <rtept lat="62.350" lon="7.560"><name>Via</name></rtept>
    <rtept lat="62.400" lon="7.610"/>
    <rtept lat="62.450" lon="7.660"><name>End</name></rtept>
  </rte>
</gpx>
"""

KML = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document><name>My KML Trip</name>
    <Placemark><name>Bakery</name><Point><coordinates>7.610,62.400,0</coordinates></Point></Placemark>
    <Placemark><name>The Line</name><LineString><coordinates>
      7.560,62.350,0 7.570,62.360,0 7.580,62.370,0 7.590,62.380,0
      7.600,62.390,0 7.610,62.400,0 7.620,62.410,0 7.630,62.420,0
    </coordinates></LineString></Placemark>
  </Document>
</kml>
"""

KURVIGER_LINK = "https://kurviger.de/en?point=62.5672,7.6875&point=62.4566,7.6664&point=62.3286,7.3462"
GOOGLE_LINK = (
    "https://www.google.com/maps/dir/62.5672,7.6875/"
    "Trollstigen+utsiktspunkt/@62.45,7.6,11z/"
    "data=!4m9!4m8!1m0!1m5!1m1!1s0x0:0x0!2m2!1d7.6664!2d62.4566!3e0"
)


def run_cli(source: str, *flags: str) -> dict:
    out = subprocess.run(
        [sys.executable, "-m", "route_converter", source, "--json", *flags],
        cwd=ROOT, capture_output=True, text=True, check=True,
    )
    return json.loads(out.stdout)


def cli_options(*flags: str) -> dict:
    """Mirror CLI flags as JS convert() options for the fixture."""
    opts: dict = {}
    it = iter(flags)
    for f in it:
        if f == "--max-stops":
            opts["maxStops"] = int(next(it))
        elif f == "--mode":
            opts["mode"] = next(it)
        elif f == "--avoid":
            opts["avoid"] = [a for a in next(it).split(",") if a]
        elif f == "--strategy":
            opts["strategy"] = next(it)
        elif f == "--start":
            opts["start"] = int(next(it))
        elif f == "--no-start":
            opts["noStart"] = True
        elif f == "--source-at-start":
            opts["sourceAtStart"] = True
    return opts


def fixture(name: str, input_spec: dict, *flags: str, source: str) -> dict:
    expected = run_cli(source, *flags)
    return {
        "name": name,
        "input": input_spec,
        "options": cli_options(*flags),
        "expected": {
            "url": expected["url"],
            "checkpoints_total": expected["checkpoints_total"],
            "checkpoints_used": expected["checkpoints_used"],
            "stops": expected["stops"],
        },
    }


def main() -> None:
    FIXTURES.mkdir(parents=True, exist_ok=True)
    cases = []

    cases.append(fixture(
        "kurviger-outbound-defaults",
        {"kind": "repo-file", "path": str(OUTBOUND.relative_to(ROOT))},
        source=str(OUTBOUND),
    ))
    cases.append(fixture(
        "kurviger-return-avoid-highways",
        {"kind": "repo-file", "path": str(RETURN.relative_to(ROOT))},
        "--avoid", "highways",
        source=str(RETURN),
    ))
    cases.append(fixture(
        "kurviger-outbound-even-8-preview",
        {"kind": "repo-file", "path": str(OUTBOUND.relative_to(ROOT))},
        "--strategy", "even", "--max-stops", "8",
        "--avoid", "tolls,highways", "--source-at-start", "--no-start",
        source=str(OUTBOUND),
    ))
    cases.append(fixture(
        "kurviger-outbound-start-delay",
        {"kind": "repo-file", "path": str(OUTBOUND.relative_to(ROOT))},
        "--start", "30", "--max-stops", "10",
        source=str(OUTBOUND),
    ))

    with tempfile.TemporaryDirectory() as td:
        for fname, text, case_name in (
            ("track.gpx", GPX_TRACK, "gpx-track-with-waypoint"),
            ("route.gpx", GPX_ROUTE, "gpx-planned-route"),
            ("trip.kml", KML, "kml-linestring-placemark"),
        ):
            p = Path(td) / fname
            p.write_text(text, encoding="utf-8")
            cases.append(fixture(
                case_name,
                {"kind": "text", "fileName": fname, "text": text},
                "--max-stops", "6",
                source=str(p),
            ))

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("doc.kml", KML)
        kmz_path = Path(td) / "trip.kmz"
        kmz_path.write_bytes(buf.getvalue())
        cases.append(fixture(
            "kmz-deflated",
            {"kind": "bytes-b64", "fileName": "trip.kmz",
             "b64": base64.b64encode(buf.getvalue()).decode()},
            "--max-stops", "6",
            source=str(kmz_path),
        ))

    cases.append(fixture(
        "kurviger-share-link",
        {"kind": "link", "url": KURVIGER_LINK},
        source=KURVIGER_LINK,
    ))
    cases.append(fixture(
        "google-full-dir-link",
        {"kind": "link", "url": GOOGLE_LINK},
        source=GOOGLE_LINK,
    ))

    out = FIXTURES / "golden.json"
    out.write_text(json.dumps(cases, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {out.relative_to(ROOT)}: {len(cases)} cases")


if __name__ == "__main__":
    main()
