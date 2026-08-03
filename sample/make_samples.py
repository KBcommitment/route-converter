"""Generate the synthetic sample routes.

The samples imitate a Kurviger/GraphHopper export — encoded 3-D polyline
geometry (lat, lon, elevation) plus named waypoints — for a made-up but
plausible ride along Norway's Golden Route: Åndalsnes up the Trollstigen
hairpins and over to Valldal. All anchor points are public tourist landmarks;
the geometry between them is synthesized (smooth interpolation plus curvature
wiggle), not real roads.

    python3 sample/make_samples.py     # rewrites the two .kurviger files
"""
from __future__ import annotations

import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent

# (lat, lon, elevation m, name-or-None) — public landmarks only.
ANCHORS = [
    (62.5672, 7.6875, 5, "Åndalsnes togstasjon, Åndalsnes, Norway"),
    (62.5210, 7.6930, 60, None),
    (62.4790, 7.6780, 180, None),
    (62.4566, 7.6664, 700, "Trollstigen utsiktspunkt, Norway"),
    (62.4300, 7.6200, 850, None),
    (62.3990, 7.5490, 620, None),
    (62.3766, 7.3902, 90, "Gudbrandsjuvet, Valldal, Norway"),
    (62.3286, 7.3462, 10, "Valldal ferjekai, Norway"),
]

POINTS_PER_LEG = 180  # dense enough to exercise checkpoint reduction
WIGGLE_DEG = 0.0016   # lateral curvature, ~100 m swings — a curvy mountain road


def synth_geometry():
    """Smooth path through the anchors with sinusoidal 'hairpin' wiggle."""
    pts = []
    for i in range(len(ANCHORS) - 1):
        la1, lo1, e1, _ = ANCHORS[i]
        la2, lo2, e2, _ = ANCHORS[i + 1]
        # Perpendicular direction for the wiggle.
        dlat, dlon = la2 - la1, lo2 - lo1
        norm = math.hypot(dlat, dlon) or 1.0
        plat, plon = -dlon / norm, dlat / norm
        # More wiggle on the steep legs (the hairpin sections).
        steep = min(1.0, abs(e2 - e1) / 400.0)
        amp = WIGGLE_DEG * (0.4 + 0.6 * steep)
        for s in range(POINTS_PER_LEG):
            t = s / POINTS_PER_LEG
            ease = t * t * (3 - 2 * t)  # smoothstep between anchors
            w = amp * math.sin(t * math.pi * 10) * math.sin(t * math.pi)
            pts.append((
                la1 + dlat * ease + plat * w,
                lo1 + dlon * ease + plon * w,
                e1 + (e2 - e1) * ease,
            ))
    la, lo, e, _ = ANCHORS[-1]
    pts.append((la, lo, e))
    return pts


def encode_polyline(points) -> str:
    """Google/GraphHopper polyline, 3-D (lat, lon, elevation·100)."""
    out = []
    prev = [0, 0, 0]
    for lat, lon, ele in points:
        for d, v in enumerate((round(lat * 1e5), round(lon * 1e5), round(ele * 100))):
            delta = v - prev[d]
            prev[d] = v
            z = ~(delta << 1) if delta < 0 else delta << 1
            while z >= 0x20:
                out.append(chr((0x20 | (z & 0x1F)) + 63))
                z >>= 5
            out.append(chr(z + 63))
    return "".join(out)


def haversine_m(a, b) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = (math.sin((la2 - la1) / 2) ** 2
         + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2)
    return 2 * 6371000.0 * math.asin(math.sqrt(h))


def build(points, anchors) -> dict:
    distance = sum(haversine_m(points[i - 1], points[i]) for i in range(1, len(points)))
    return {
        "info": {"copyrights": ["synthetic sample route — not real roads"]},
        "paths": [{
            "distance": round(distance, 1),
            "time": int(distance / 13.9 * 1000),  # ~50 km/h
            "points_encoded": True,
            "elevation": True,
            "points": encode_polyline(points),
            "waypoints": [
                {"latitude": la, "longitude": lo, "address": nm}
                for la, lo, _e, nm in anchors if nm
            ],
        }],
    }


def main() -> None:
    pts = synth_geometry()
    out = HERE / "Aandalsnes - Trollstigen - Valldal.kurviger"
    ret = HERE / "Aandalsnes - Trollstigen - Valldal - return.kurviger"
    out.write_text(json.dumps(build(pts, ANCHORS)), encoding="utf-8")
    ret.write_text(
        json.dumps(build(pts[::-1], ANCHORS[::-1])), encoding="utf-8"
    )
    km = build(pts, ANCHORS)["paths"][0]["distance"] / 1000
    print(f"wrote {out.name} and return leg: {len(pts)} points, {km:.1f} km")


if __name__ == "__main__":
    main()
