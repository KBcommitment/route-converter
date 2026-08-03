"""Command-line interface: route file/link -> Apple Maps directions URL."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from typing import List, Optional, Sequence

from .apple_maps import AVOID_OPTIONS, build_url
from .parsers import parse_source
from .simplify import reduce_checkpoints


def _print_qr(url: str) -> None:
    try:
        import qrcode  # optional dependency
    except ImportError:
        print(
            "(install 'qrcode' for a scannable QR: pip install qrcode)",
            file=sys.stderr,
        )
        return
    qr = qrcode.QRCode(border=1)
    qr.add_data(url)
    qr.make()
    qr.print_ascii(invert=True)


def _parse_avoid(value: Optional[str]) -> List[str]:
    if not value:
        return []
    items = [v.strip() for v in value.split(",") if v.strip()]
    bad = [v for v in items if v not in AVOID_OPTIONS]
    if bad:
        raise SystemExit(
            f"error: unknown --avoid option(s) {bad}; allowed: {sorted(AVOID_OPTIONS)}"
        )
    return items


def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="route2maps",
        description="Convert a GPX/KML/KMZ/Kurviger route (file or link) into an "
        "Apple Maps directions URL (unified Maps URL, iOS 18.4+).",
    )
    ap.add_argument(
        "input",
        help="route file (.kurviger/.gpx/.kml/.kmz) or a Kurviger/Google Maps link",
    )
    ap.add_argument(
        "--max-stops",
        type=int,
        default=15,
        help="max stops Apple sees, including your current location when routing "
        "from it (Apple caps a route at ~15; default: 15)",
    )
    ap.add_argument(
        "--mode",
        choices=["drive", "walk", "transit", "cycle"],
        default="drive",
        help="transport mode (multi-stop is driving only; default: drive)",
    )
    ap.add_argument(
        "--avoid",
        default="",
        help="comma-separated: " + ",".join(sorted(AVOID_OPTIONS))
        + " (e.g. 'highways' to keep a curvy ride off the autobahn)",
    )
    ap.add_argument(
        "--strategy",
        choices=["hybrid", "even"],
        default="hybrid",
        help="checkpoint placement: hybrid = put stops on route deviations "
        "(detours/bends); even = spread evenly by distance (default: hybrid)",
    )
    ap.add_argument(
        "--source-at-start",
        action="store_true",
        help="pin the route's origin to its first point instead of the device's "
        "current location. Makes the link preview-only: Apple Maps shows 'Steps' "
        "instead of 'Go' and CarPlay reports 'Directions Not Available'",
    )
    ap.add_argument(
        "--start",
        type=int,
        default=0,
        metavar="SECONDS",
        help="begin turn-by-turn navigation after SECONDS (default: 0, immediately)",
    )
    ap.add_argument(
        "--no-start",
        action="store_true",
        help="open the route as a preview instead of navigating. Starting a "
        "multi-stop route by hand is exactly what fails: Maps offers only a "
        "'Steps' list and CarPlay reports 'Directions Not Available'",
    )
    ap.add_argument(
        "--scheme",
        choices=["https", "maps"],
        default="https",
        help="https = universal maps.apple.com link; maps = maps:// app scheme",
    )
    ap.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    ap.add_argument("--qr", action="store_true", help="print a scannable QR code of the link")
    ap.add_argument(
        "--open",
        action="store_true",
        dest="open_url",
        help="open the link locally (macOS 'open')",
    )
    return ap


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    avoid = _parse_avoid(args.avoid)

    route = parse_source(args.input)
    total = len(route.checkpoints)
    # Routing from the current location spends one of Apple's ~15 stops on that
    # location, so one fewer point can be sampled from the route itself.
    budget = args.max_stops if args.source_at_start else args.max_stops - 1
    if budget < 1:
        raise SystemExit(f"error: --max-stops {args.max_stops} leaves no room for the route")
    used = reduce_checkpoints(route.checkpoints, budget, strategy=args.strategy)
    url = build_url(
        used,
        mode=args.mode,
        from_current=not args.source_at_start,
        avoid=avoid,
        scheme=args.scheme,
        start=None if args.no_start else args.start,
    )

    if args.json:
        print(
            json.dumps(
                {
                    "name": route.name,
                    "source_format": route.source_format,
                    "mode": args.mode,
                    "avoid": avoid,
                    "strategy": args.strategy,
                    "origin": "route-start" if args.source_at_start else "current-location",
                    "start_delay": None if args.no_start else args.start,
                    "checkpoints_total": total,
                    "checkpoints_used": len(used),
                    "stops": [
                        {"lat": c.lat, "lon": c.lon, "name": c.name} for c in used
                    ],
                    "url": url,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        capped = "  (capped for Apple Maps)" if total > len(used) else ""
        print(f"Route:       {route.name or '(unnamed)'}  [{route.source_format}]")
        print(f"Checkpoints: {total} found -> {len(used)} used{capped}")
        print(f"Mode:        {args.mode}" + (f"  avoid: {','.join(avoid)}" if avoid else ""))
        origin = "route's first point" if args.source_at_start else "your current location"
        print(f"Starts at:   {origin}")
        if not args.no_start:
            when = "immediately" if args.start == 0 else f"after {args.start}s"
            print(f"Navigation:  starts {when} on open")
        print()
        print(url)
        print()
        named = [c for c in used if c.name]
        if named:
            print("Named stops kept:")
            for c in named:
                print(f"  - {c.name}  ({c.lat:.5f}, {c.lon:.5f})")
            print()
        if args.mode != "drive" and len(used) > 2:
            print(
                "Note: Apple Maps multi-stop routing is driving only; extra "
                "waypoints may be ignored in this mode.",
                file=sys.stderr,
            )
        if args.no_start:
            print(
                "Note: --no-start opens a preview. Starting a multi-stop route "
                "by hand is what fails — Maps offers only a 'Steps' list and "
                "CarPlay reports 'Directions Not Available'.",
                file=sys.stderr,
            )
        print(
            "Tip: open this link on your iPhone (iOS 18.4+) standing at the "
            "route's start; navigation begins on its own -> CarPlay picks it up."
        )

    if args.qr:
        print()
        _print_qr(url)
    if args.open_url:
        subprocess.run(["open", url], check=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
