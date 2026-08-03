"""Parse Kurviger routes — the native ``.kurviger`` JSON file and share links.

The ``.kurviger`` file is the richest source: it is a GraphHopper response that
carries the full road geometry (an encoded polyline) plus the planned
``waypoints``. We decode the dense geometry so that Apple Maps can be forced to
follow the curvy path, and tag the points nearest each planned waypoint as
``significant`` so they always survive reduction.
"""
from __future__ import annotations

from typing import List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

import json

from ..models import Checkpoint, Route
from .polyline import decode as decode_polyline


def parse_kurviger_file(text: str, name: Optional[str] = None) -> Route:
    data = json.loads(text)
    paths = data.get("paths")
    if not paths:
        raise ValueError("Not a Kurviger route file: no 'paths' found")
    path = paths[0]

    geometry = _decode_geometry(path)
    waypoints = path.get("waypoints") or []
    checkpoints = _build_checkpoints(geometry, waypoints)
    return Route(checkpoints=checkpoints, name=name, source_format="kurviger")


def _decode_geometry(path) -> List[Tuple[float, float]]:
    pts = path.get("points")
    if pts is None:
        raise ValueError("Kurviger path has no 'points' geometry")
    if path.get("points_encoded", True):
        if not isinstance(pts, str):
            raise ValueError("points_encoded is true but 'points' is not a string")
        return decode_polyline(pts, with_elevation=bool(path.get("elevation")))
    # GeoJSON-style: {"coordinates": [[lon, lat, (ele)], ...]} or a bare list.
    coords = pts["coordinates"] if isinstance(pts, dict) else pts
    return [(c[1], c[0]) for c in coords]


def _build_checkpoints(geometry, waypoints) -> List[Checkpoint]:
    checkpoints = [Checkpoint(lat=lat, lon=lon) for (lat, lon) in geometry]
    for wp in waypoints:
        lat = wp.get("latitude")
        lon = wp.get("longitude")
        if lat is None or lon is None:
            continue
        idx = _nearest_index(geometry, lat, lon)
        checkpoints[idx].significant = True
        if wp.get("address"):
            checkpoints[idx].name = wp["address"]
    checkpoints[0].significant = True
    checkpoints[-1].significant = True
    return checkpoints


def _nearest_index(geometry, lat: float, lon: float) -> int:
    best_i, best_d = 0, float("inf")
    for i, (glat, glon) in enumerate(geometry):
        d = (glat - lat) ** 2 + (glon - lon) ** 2
        if d < best_d:
            best_d, best_i = d, i
    return best_i


def parse_kurviger_link(url: str, name: Optional[str] = None) -> Route:
    """Best-effort decode of a kurviger.de share link.

    Older share links expose waypoints as repeated ``point=lat,lon`` query
    params. Newer links can carry an opaque encoded payload with no geometry —
    in that case export the route as a ``.kurviger`` or GPX file instead.
    """
    query = parse_qs(urlparse(url).query)
    raw = query.get("point") or query.get("waypoints") or []
    coords: List[Tuple[float, float]] = []
    for item in raw:
        for piece in item.split(";"):
            piece = piece.strip()
            if not piece:
                continue
            lat_str, _, lon_str = piece.partition(",")
            coords.append((float(lat_str), float(lon_str)))

    if not coords:
        raise ValueError(
            "Could not extract waypoints from this Kurviger link. Export the "
            "route as a .kurviger or GPX file and pass that instead."
        )

    checkpoints = [Checkpoint(lat, lon, significant=True) for lat, lon in coords]
    return Route(checkpoints=checkpoints, name=name, source_format="kurviger-link")
