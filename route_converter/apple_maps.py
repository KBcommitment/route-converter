"""Build an Apple Maps directions URL from a list of checkpoints.

Uses the **unified Maps URL** format (iOS 18.4+ / recent macOS), which is the
first Apple Maps URL scheme to support multi-stop routes::

    https://maps.apple.com/directions
        ?source=<lat,lng>
        &waypoint=<lat,lng>        # repeatable, in visiting order
        &waypoint=<lat,lng>
        &destination=<lat,lng>
        &mode=driving
        &avoid=highways,tolls      # optional
        &start=0                   # optional: begin navigating after N seconds

Notes / platform limits:
- Apple Maps caps a route at ~15 stops, and multi-stop is **driving only**.
- **``start`` is what actually begins turn-by-turn navigation.** Without it the
  link only opens a route *preview*, and the user has to start navigation from
  the Maps UI — which is where a multi-stop route gets stuck: the preview offers
  a "Steps" button (the written step list), and CarPlay reports "Directions Not
  Available". Verified in the iOS 26.2 Simulator: ``start=0`` starts turn-by-turn
  on a 14-stop route, with or without ``source``.
- Omitting ``source`` makes the origin the device's location ("My Location"),
  which is also what Apple documents as the condition for Maps offering "Go"
  rather than "Steps" — so the route is navigable from where the rider is
  standing rather than being a preview of somebody else's trip.
- The older ``?saddr=&daddr=&dirflg=`` scheme supported a single destination
  only (no waypoints) and ``daddr=lat,lng`` regressed on iOS 18.4+.
"""
from __future__ import annotations

from typing import List, Optional, Sequence

from .models import Checkpoint

_MODES = {
    "drive": "driving",
    "driving": "driving",
    "walk": "walking",
    "walking": "walking",
    "transit": "transit",
    "cycle": "cycling",
    "cycling": "cycling",
    "bike": "cycling",
}

AVOID_OPTIONS = {"tolls", "highways", "busy-roads", "stairs"}


def _coord(cp: Checkpoint) -> str:
    # lat,lng with no spaces — all characters are URL-safe, no encoding needed.
    return f"{cp.lat:.6f},{cp.lon:.6f}"


def build_url(
    points: Sequence[Checkpoint],
    mode: str = "drive",
    from_current: bool = False,
    avoid: Optional[Sequence[str]] = None,
    scheme: str = "https",
    start: Optional[int] = None,
) -> str:
    """Return a unified Apple Maps directions URL visiting ``points`` in order.

    ``from_current`` omits ``source`` so Maps routes from the device's location
    — required for turn-by-turn (see the module docstring). ``start`` adds
    ``start=N``, which begins navigating after ``N`` seconds.
    """
    if not points:
        raise ValueError("Cannot build an Apple Maps URL with no checkpoints")

    if start is not None and start < 0:
        raise ValueError(f"start must be a non-negative number of seconds, got {start}")

    mode_val = _MODES.get(mode)
    if mode_val is None:
        raise ValueError(f"Unknown mode {mode!r}; use drive, walk, transit, or cycle")

    if avoid:
        bad = [a for a in avoid if a not in AVOID_OPTIONS]
        if bad:
            raise ValueError(
                f"Unknown avoid option(s): {bad}. Allowed: {sorted(AVOID_OPTIONS)}"
            )

    base = "https://maps.apple.com/directions" if scheme == "https" else "maps://directions"

    pts = list(points)
    use_source = (not from_current) and len(pts) > 1
    if use_source:
        source: Optional[Checkpoint] = pts[0]
        rest = pts[1:]
    else:
        source = None
        rest = pts

    *waypoints, destination = rest  # rest always has at least one element

    params: List[str] = []
    if source is not None:
        params.append(f"source={_coord(source)}")
    for w in waypoints:
        params.append(f"waypoint={_coord(w)}")
    params.append(f"destination={_coord(destination)}")
    params.append(f"mode={mode_val}")
    if avoid:
        params.append("avoid=" + ",".join(avoid))
    if start is not None:
        params.append(f"start={start}")

    return base + "?" + "&".join(params)
