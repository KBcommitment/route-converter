"""Parse GPX files (the de-facto interchange format for routes and tracks).

Priority of geometry sources within a GPX file:
1. ``<rte>/<rtept>`` — a planned route (named points are real waypoints).
2. ``<trk>/<trkseg>/<trkpt>`` — a recorded track (dense geometry).
3. ``<wpt>`` — standalone waypoints, used only if there is no route/track.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import List, Optional

from ..models import Checkpoint, Route


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _findall(root, name: str):
    return [e for e in root.iter() if _local(e.tag) == name]


def _text_child(el, name: str) -> Optional[str]:
    for c in el:
        if _local(c.tag) == name:
            return (c.text or "").strip() or None
    return None


def _point(el) -> Checkpoint:
    lat = float(el.get("lat"))
    lon = float(el.get("lon"))
    nm = _text_child(el, "name")
    return Checkpoint(lat=lat, lon=lon, name=nm, significant=bool(nm))


def _nearest(points: List[Checkpoint], target: Checkpoint) -> int:
    return min(
        range(len(points)),
        key=lambda k: (points[k].lat - target.lat) ** 2
        + (points[k].lon - target.lon) ** 2,
    )


def parse_gpx(text: str, name: Optional[str] = None) -> Route:
    root = ET.fromstring(text)
    rtepts = [_point(e) for e in _findall(root, "rtept")]
    trkpts = [_point(e) for e in _findall(root, "trkpt")]
    wpts = [_point(e) for e in _findall(root, "wpt")]

    if rtepts:
        base = rtepts
    elif trkpts:
        base = trkpts
    else:
        base = wpts

    if not base:
        raise ValueError(
            "GPX file contains no route points, track points, or waypoints"
        )

    # A dense track has no inherent named stops; pull names from any <wpt>.
    if base is trkpts and wpts:
        for w in wpts:
            i = _nearest(base, w)
            base[i].significant = True
            base[i].name = w.name or base[i].name

    base[0].significant = True
    base[-1].significant = True

    return Route(
        checkpoints=base,
        name=name or _route_name(root),
        source_format="gpx",
    )


def _route_name(root) -> Optional[str]:
    for parent in ("rte", "trk", "metadata"):
        for el in _findall(root, parent):
            nm = _text_child(el, "name")
            if nm:
                return nm
    return None
