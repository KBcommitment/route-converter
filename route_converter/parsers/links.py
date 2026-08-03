"""Best-effort extraction of waypoints from a Google Maps directions link.

Google does not publish a stable URL format, but a directions URL generally
carries enough to reconstruct the stops:

- ``/dir/<A>/<B>/...`` path segments are the stops in visiting order. A segment
  is either an explicit ``lat,lng`` or a place name.
- The ``data=`` payload holds the resolved place coordinates, most commonly as
  ``!1d<lng>!2d<lat>`` groups (note: longitude first), in the same order.

Named segments are matched to ``data=`` coordinates positionally. Short links
(``maps.app.goo.gl``) are expanded via an HTTP redirect first. For the most
reliable result, export the route as GPX/KML instead.
"""
from __future__ import annotations

import re
import urllib.request
from typing import List, Optional, Tuple
from urllib.parse import unquote, urlparse

from ..models import Checkpoint, Route

_DIR_COORD = re.compile(r"^-?\d{1,3}(?:\.\d+)?,-?\d{1,3}(?:\.\d+)?$")
_PLACE_LNGLAT = re.compile(r"!1d(-?\d+\.\d+)!2d(-?\d+\.\d+)")  # (lng, lat)
_PLACE_LATLNG = re.compile(r"!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)")  # (lat, lng)
_SHORT_HOSTS = ("goo.gl",)  # covers goo.gl and maps.app.goo.gl


def _expand_short_link(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if not any(h in host for h in _SHORT_HOSTS):
        return url
    req = urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0 (Macintosh)"}
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.geturl()
    except OSError as exc:
        raise ValueError(
            f"Could not expand the short link {url!r} ({exc}). Open it in a "
            "browser, copy the full google.com/maps/dir/... URL, and pass that."
        )


def _resolved_place_coords(url: str) -> List[Tuple[float, float]]:
    coords = [(float(lat), float(lng)) for lng, lat in _PLACE_LNGLAT.findall(url)]
    if not coords:
        coords = [(float(lat), float(lng)) for lat, lng in _PLACE_LATLNG.findall(url)]
    return coords


def parse_google_maps_link(url: str, name: Optional[str] = None) -> Route:
    url = _expand_short_link(url.strip())
    parsed = urlparse(url)
    place_coords = _resolved_place_coords(url)

    coords: List[Tuple[float, float]] = []
    if "/dir/" in parsed.path:
        place_iter = iter(place_coords)
        for seg in parsed.path.split("/dir/", 1)[1].split("/"):
            seg = unquote(seg)
            if not seg or seg.startswith("@") or seg.startswith("data="):
                continue
            if _DIR_COORD.match(seg):
                lat, lon = seg.split(",")
                coords.append((float(lat), float(lon)))
            else:
                # A named place: take the next resolved coordinate in order.
                nxt = next(place_iter, None)
                if nxt is not None:
                    coords.append(nxt)
    else:
        coords = place_coords

    if not coords:
        raise ValueError(
            "Could not extract coordinates from this Google Maps link. Open the "
            "route in Google Maps, export/share it as GPX or KML, and pass that "
            "file instead."
        )

    checkpoints = [Checkpoint(lat, lon, significant=True) for lat, lon in coords]
    return Route(
        checkpoints=checkpoints, name=name, source_format="google-maps-link"
    )
