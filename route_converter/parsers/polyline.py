"""Decode GraphHopper / Google encoded polylines.

Kurviger routes are computed by GraphHopper, which encodes the path geometry as
a Google-style polyline. When a route carries elevation data (``elevation:
true``) the encoding is **3-dimensional** (lat, lon, elevation) rather than the
usual 2-dimensional (lat, lon) — the third value must be consumed per point or
every coordinate after the first comes out garbled.
"""
from __future__ import annotations

from typing import List, Tuple


def decode(
    encoded: str,
    with_elevation: bool = False,
    precision: float = 1e5,
) -> List[Tuple[float, float]]:
    """Decode an encoded polyline into a list of ``(lat, lon)`` tuples.

    Elevation, when present, is consumed so coordinates stay aligned but is not
    returned — Apple Maps does not use it.
    """
    dims = 3 if with_elevation else 2
    coords: List[Tuple[float, float]] = []
    i = 0
    n = len(encoded)
    lat = lon = ele = 0

    while i < n:
        deltas = [0, 0, 0]
        for d in range(dims):
            shift = 0
            result = 0
            while True:
                b = ord(encoded[i]) - 63
                i += 1
                result |= (b & 0x1F) << shift
                shift += 5
                if b < 0x20:
                    break
            deltas[d] = ~(result >> 1) if (result & 1) else (result >> 1)
        lat += deltas[0]
        lon += deltas[1]
        ele += deltas[2]
        coords.append((lat / precision, lon / precision))

    return coords
