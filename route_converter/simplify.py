"""Reduce a dense route down to Apple Maps' stop limit.

Apple Maps caps a route at ~15 stops and re-routes between them with its own
engine, so the few waypoints we send have to do a lot of work. Two strategies:

- ``"even"``    — spread waypoints evenly *by distance*. Bounds the largest gap
                  (the main thing that lets Apple wander onto a different road),
                  but can miss a short detour that falls between two stops.
- ``"hybrid"``  — (default) divide the route into evenly-sized cells (still
                  bounding the gap) and, within each cell, place the waypoint on
                  the point of **maximum deviation** — the apex of a detour such
                  as a loop through a town to avoid a bypass. Straight cells fall
                  back to even spacing. This captures the deviations that make a
                  Kurviger route different from Apple's default, within the same
                  stop budget.

Both always keep the first & last point and every ``significant`` waypoint.
"""
from __future__ import annotations

import bisect
import math
from typing import List, Sequence, Set, Tuple

from .models import Checkpoint

# Below this lateral deviation (in scaled degrees, ~5 m) a cell is treated as
# straight and the waypoint is placed at its midpoint for even spacing.
_STRAIGHT_EPS = 5e-5


def _dedupe(points: Sequence[Checkpoint], eps: float = 1e-6) -> List[Checkpoint]:
    """Drop consecutive (near-)duplicate points, preserving significance/name."""
    out: List[Checkpoint] = []
    for p in points:
        if out and abs(out[-1].lat - p.lat) < eps and abs(out[-1].lon - p.lon) < eps:
            if p.significant and not out[-1].significant:
                out[-1].significant = True
            if p.name and not out[-1].name:
                out[-1].name = p.name
            continue
        out.append(p)
    return out


def _haversine_km(a: Checkpoint, b: Checkpoint) -> float:
    r = 6371.0
    la1, lo1, la2, lo2 = map(math.radians, (a.lat, a.lon, b.lat, b.lon))
    h = (
        math.sin((la2 - la1) / 2) ** 2
        + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    )
    return 2 * r * math.asin(math.sqrt(h))


def _cumulative(points: Sequence[Checkpoint]) -> List[float]:
    cum = [0.0]
    for i in range(1, len(points)):
        cum.append(cum[-1] + _haversine_km(points[i - 1], points[i]))
    return cum


def _allocate(budget: int, weights: Sequence[float]) -> List[int]:
    """Apportion ``budget`` integer slots across segments by weight (largest remainder)."""
    total = sum(weights) or 1.0
    raw = [budget * w / total for w in weights]
    base = [int(math.floor(x)) for x in raw]
    remainder = budget - sum(base)
    order = sorted(range(len(weights)), key=lambda i: raw[i] - base[i], reverse=True)
    for i in order[:remainder]:
        base[i] += 1
    return base


def _nearest_arc_index(cum: Sequence[float], lo: int, hi: int, target: float) -> int:
    """Index in the open interval (lo, hi) whose arc length is closest to target."""
    best, best_d = -1, math.inf
    for j in range(lo + 1, hi):
        d = abs(cum[j] - target)
        if d < best_d:
            best_d, best = d, j
    return best


def _idx_at(cum: Sequence[float], arc: float, lo: int, hi: int) -> int:
    """First geometry index in [lo, hi] whose arc length is >= ``arc``."""
    i = bisect.bisect_left(cum, arc, lo, hi + 1)
    return min(max(i, lo), hi)


def _perp(p: Tuple[float, float], a: Tuple[float, float], b: Tuple[float, float]) -> float:
    """Perpendicular distance from (lat,lon) ``p`` to segment ``a``-``b``.

    Longitude is scaled by cos(latitude) so the deviation is locally isotropic;
    units are scaled degrees (only relative magnitude matters here).
    """
    coslat = math.cos(math.radians(a[0]))
    ax, ay = a[1] * coslat, a[0]
    bx, by = b[1] * coslat, b[0]
    px, py = p[1] * coslat, p[0]
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def _place_even(cum: Sequence[float], a: int, b: int, k: int, keep: Set[int]) -> None:
    span = cum[b] - cum[a]
    for m in range(1, k + 1):
        target = cum[a] + span * m / (k + 1)
        j = _nearest_arc_index(cum, a, b, target)
        if j != -1:
            keep.add(j)


def _place_hybrid(
    pts: Sequence[Checkpoint], cum: Sequence[float], a: int, b: int, k: int, keep: Set[int]
) -> None:
    span = cum[b] - cum[a]
    for c in range(k):
        lo = _idx_at(cum, cum[a] + span * c / k, a, b)
        hi = _idx_at(cum, cum[a] + span * (c + 1) / k, a, b)
        if hi <= lo:
            hi = min(lo + 1, b)
        chord_a = (pts[lo].lat, pts[lo].lon)
        chord_b = (pts[hi].lat, pts[hi].lon)
        best, best_d = lo, -1.0
        for j in range(lo, hi + 1):
            d = _perp((pts[j].lat, pts[j].lon), chord_a, chord_b)
            if d > best_d:
                best_d, best = d, j
        if best_d < _STRAIGHT_EPS:  # straight cell: keep even spacing
            best = (lo + hi) // 2
        keep.add(best)


def reduce_checkpoints(
    points: Sequence[Checkpoint], max_points: int, strategy: str = "hybrid"
) -> List[Checkpoint]:
    """Reduce ``points`` to at most ``max_points`` checkpoints.

    Always keeps the first & last point and every ``significant`` waypoint, then
    distributes the remaining budget across the gaps between kept points
    (proportional to gap length) using ``strategy`` ("hybrid" or "even").
    """
    pts = _dedupe(points)
    n = len(pts)
    if max_points <= 0 or n <= max_points:
        return pts

    cum = _cumulative(pts)
    total = cum[-1] or 1.0
    mandatory = sorted({0, n - 1} | {i for i, p in enumerate(pts) if p.significant})

    # More named waypoints than the budget: keep endpoints + an evenly (by
    # distance) spaced subset of the named points.
    if len(mandatory) >= max_points:
        keep = {0, n - 1}
        inner = [i for i in mandatory if i not in (0, n - 1)]
        budget = max_points - len(keep)
        for m in range(1, budget + 1):
            target = total * m / (budget + 1)
            keep.add(min(inner, key=lambda i: abs(cum[i] - target)))
        return [pts[i] for i in sorted(keep)]

    budget = max_points - len(mandatory)
    keep: Set[int] = set(mandatory)
    segments = list(zip(mandatory[:-1], mandatory[1:]))
    weights = [cum[b] - cum[a] for a, b in segments]
    for (a, b), k in zip(segments, _allocate(budget, weights)):
        if k <= 0 or b <= a + 1:
            continue
        if strategy == "even":
            _place_even(cum, a, b, k, keep)
        else:
            _place_hybrid(pts, cum, a, b, k, keep)
    return [pts[i] for i in sorted(keep)]
